"""Security scan orchestration, dashboard aggregation and finding review.

Scans are explicit and run asynchronously through Celery.  They never intercept
normal model execution; the optional ``blocking_enabled`` flag only labels
findings as blocking and requires a recorded reason.
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.projects.services import project_for_user
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from integrations.security import registry
from integrations.security.base import SEVERITY_RANK, SecurityDetection

from .models import (
    SecurityClassification,
    SecurityDisposition,
    SecurityFinding,
    SecurityFindingEvent,
    SecurityScan,
    SecuritySeverity,
    SecurityTestResult,
    SecurityTestRun,
)
from .targets import ScanSegment, collect_segments, resolve_target

TERMINAL_STATUSES = (SecurityScan.Status.COMPLETED, SecurityScan.Status.FAILED)
SEVERITY_ORDER = [value for value, _ in SecuritySeverity.choices]
STATUSES = {value for value, _ in SecurityFinding.Status.choices}
logger = logging.getLogger(__name__)


def _project(actor, project_id):
    return project_for_user(actor, project_id, Membership.Role.VIEWER)


def scan_for_user(user, scan_id, minimum_role=Membership.Role.VIEWER) -> SecurityScan:
    scan = (
        SecurityScan.objects.select_related(
            "project",
            "project__workspace",
            "dataset",
            "prompt",
            "execution",
            "created_by",
        )
        .filter(pk=scan_id)
        .first()
    )
    if scan is None:
        raise NotFound("Security scan not found.")
    require_membership(user, scan.project.workspace_id, minimum_role)
    return scan


def finding_for_user(
    user, finding_id, minimum_role=Membership.Role.VIEWER
) -> SecurityFinding:
    finding = (
        SecurityFinding.objects.select_related(
            "project",
            "project__workspace",
            "scan",
            "execution",
            "execution_result",
            "reviewed_by",
        )
        .prefetch_related("events__actor")
        .filter(pk=finding_id)
        .first()
    )
    if finding is None:
        raise NotFound("Security finding not found.")
    require_membership(user, finding.project.workspace_id, minimum_role)
    return finding


def list_scans(*, user, project_id, status=None, limit=100):
    project = _project(user, project_id)
    rows = SecurityScan.objects.filter(project=project).select_related(
        "created_by", "dataset", "prompt", "execution"
    )
    if status in SecurityScan.Status.values:
        rows = rows.filter(status=status)
    return rows.order_by("-created_at")[:limit]


def list_findings(
    *,
    user,
    project_id,
    status=None,
    severity=None,
    category=None,
    check=None,
    scan_id=None,
    limit=500,
):
    project = _project(user, project_id)
    rows = (
        SecurityFinding.objects.filter(project=project)
        .select_related("scan", "execution", "execution_result", "reviewed_by")
        .prefetch_related("events__actor")
    )
    if status in STATUSES:
        rows = rows.filter(status=status)
    if severity in SecuritySeverity.values:
        rows = rows.filter(severity=severity)
    if category:
        rows = rows.filter(category=category[:100])
    if check:
        rows = rows.filter(check_key=check[:32])
    if scan_id:
        try:
            UUID(str(scan_id))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"scan": "Invalid security scan id."}) from exc
        rows = rows.filter(scan_id=scan_id)
    return rows.order_by("-detected_at", "-id")[:limit]


def _comparison_key(finding: SecurityFinding) -> tuple[str, str, str, str, str]:
    """Stable detection identity across two scans of the same resource."""
    return (
        finding.resource_type,
        finding.resource_id,
        finding.location,
        finding.check_key,
        finding.category,
    )


def _severity_order(finding: SecurityFinding) -> tuple[int, str, str]:
    return (
        -SEVERITY_RANK.get(finding.severity, 0),
        finding.category,
        finding.resource_label,
    )


def compare_scans(*, user, project_id, baseline_id, current_id) -> dict:
    """Compare detection identities between two scans of the same target."""
    project = _project(user, project_id)
    baseline = scan_for_user(user, baseline_id)
    current = scan_for_user(user, current_id)
    if baseline.project_id != project.pk or current.project_id != project.pk:
        raise NotFound("Security scan not found.")
    if baseline.pk == current.pk:
        raise ValidationError(
            {"current": "Choose two different scans to compare."}
        )
    if (
        baseline.target_type != current.target_type
        or baseline.target_identifier != current.target_identifier
    ):
        raise ValidationError(
            {
                "current": (
                    "Both scans must target the same resource. "
                    "Rerun a scan to compare the same target over time."
                )
            }
        )

    findings = (
        SecurityFinding.objects.filter(scan__in=[baseline, current])
        .select_related("scan", "execution", "execution_result", "reviewed_by")
        .prefetch_related("events__actor")
    )
    baseline_map = {
        _comparison_key(finding): finding
        for finding in findings
        if finding.scan_id == baseline.pk
    }
    current_map = {
        _comparison_key(finding): finding
        for finding in findings
        if finding.scan_id == current.pk
    }

    new_findings = sorted(
        (finding for key, finding in current_map.items() if key not in baseline_map),
        key=_severity_order,
    )
    resolved_findings = sorted(
        (finding for key, finding in baseline_map.items() if key not in current_map),
        key=_severity_order,
    )
    persisting = []
    for key, current_finding in current_map.items():
        baseline_finding = baseline_map.get(key)
        if baseline_finding is None:
            continue
        changed_fields = [
            field
            for field in ("severity", "disposition", "status", "classification")
            if getattr(baseline_finding, field) != getattr(current_finding, field)
        ]
        persisting.append(
            {
                "baseline": baseline_finding,
                "current": current_finding,
                "changed_fields": changed_fields,
            }
        )
    persisting.sort(key=lambda item: _severity_order(item["current"]))

    checks_match = set(baseline.checks or []) == set(current.checks or [])
    target_version_changed = baseline.target_version != current.target_version
    warnings = []
    if not checks_match:
        warnings.append(
            "The scans used different checks, so a difference can come from the "
            "check selection rather than the resource."
        )
    if target_version_changed:
        warnings.append(
            "The target version changed between scans. Detection identities can "
            "change when a prompt or dataset version is updated."
        )
    warnings.append(
        "A finding absent from the current scan is not proof that the issue was fixed. "
        "Detectors are heuristic and can miss the same or a different problem."
    )

    return {
        "project": str(project.pk),
        "baseline_scan": baseline,
        "current_scan": current,
        "counts": {
            "baseline_total": len(baseline_map),
            "current_total": len(current_map),
            "new": len(new_findings),
            "resolved": len(resolved_findings),
            "persisting": len(persisting),
            "changed": sum(1 for item in persisting if item["changed_fields"]),
        },
        "target": {
            "type": current.target_type,
            "identifier": current.target_identifier,
            "label": current.target_label,
            "baseline_version": baseline.target_version,
            "current_version": current.target_version,
            "version_changed": target_version_changed,
        },
        "checks": {
            "baseline": list(baseline.checks or []),
            "current": list(current.checks or []),
            "match": checks_match,
        },
        "warnings": warnings,
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
        "persisting": persisting,
    }


def _validated_pii_categories(checks, config) -> list[str]:
    if "pii" not in checks:
        return []
    from integrations.security.pii import normalize_categories

    try:
        return list(normalize_categories((config or {}).get("pii_categories")))
    except ValueError as exc:
        raise ValidationError({"pii_categories": str(exc)}) from exc


def _validate_blocking(validated_data) -> tuple[bool, str, str]:
    enabled = bool(validated_data.get("blocking_enabled", False))
    severity = validated_data.get("blocking_severity") or SecuritySeverity.HIGH
    if severity not in SecuritySeverity.values:
        raise ValidationError({"blocking_severity": "Unknown severity."})
    reason = str(validated_data.get("blocking_reason") or "").strip()
    if enabled and not reason:
        raise ValidationError(
            {
                "blocking_reason": (
                    "Explain why this scan opts into blocking disposition. "
                    "Scans do not interrupt execution automatically."
                )
            }
        )
    return enabled, severity, reason


def _target_fields(target_type: str, target) -> dict:
    if target_type == SecurityScan.TargetType.DATASET:
        return {"dataset": target, "prompt": None, "execution": None}
    if target_type == SecurityScan.TargetType.PROMPT:
        return {"dataset": None, "prompt": target, "execution": None}
    if target_type == SecurityScan.TargetType.EXECUTION:
        return {"dataset": None, "prompt": None, "execution": target}
    raise ValidationError({"target_type": "Unsupported security scan target."})


@transaction.atomic
def create_scan(*, actor, project_id, validated_data) -> SecurityScan:
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    target_type = validated_data["target_type"]
    target = resolve_target(
        user=actor,
        project_id=project.pk,
        target_type=target_type,
        target_id=validated_data["target_id"],
    )
    try:
        checks = registry.validate_checks(validated_data.get("checks"))
    except ValueError as exc:
        raise ValidationError({"checks": str(exc)}) from exc
    pii_categories = _validated_pii_categories(checks, validated_data.get("config"))
    blocking_enabled, blocking_severity, blocking_reason = _validate_blocking(
        validated_data
    )
    scan_config = dict(validated_data.get("config") or {})
    scan_config.update(
        {"pii_categories": pii_categories, "target_truncated": target.truncated}
    )
    scan = SecurityScan.objects.create(
        project=project,
        target_type=target_type,
        **{
            **_target_fields(target_type, target.target),
            "target_identifier": target.target_id,
        },
        target_label=target.target_label[:240],
        target_version=target.target_version[:80],
        checks=list(checks),
        config=scan_config,
        blocking_enabled=blocking_enabled,
        blocking_severity=blocking_severity,
        blocking_reason=blocking_reason[:2000],
        total_items=len(target.segments),
        created_by=actor,
    )
    return scan


def _mark_failed(scan: SecurityScan, category: str, message: str) -> None:
    scan.status = SecurityScan.Status.FAILED
    scan.error = {"category": category, "message": message}
    scan.completed_at = timezone.now()
    scan.save(update_fields=["status", "error", "completed_at"])


def enqueue_scan(scan: SecurityScan) -> SecurityScan:
    from .tasks import run_security_scan

    try:
        async_result = run_security_scan.delay(str(scan.pk))
    except Exception:  # noqa: BLE001 - broker failures stay visible to the user
        _mark_failed(
            scan,
            "queue_unavailable",
            "The security scan could not be queued. Check the worker and broker.",
        )
        scan.refresh_from_db()
        return scan

    task_id = getattr(async_result, "id", None)
    if task_id:
        SecurityScan.objects.filter(
            pk=scan.pk, status=SecurityScan.Status.QUEUED
        ).update(task_id=str(task_id)[:200])
    scan.refresh_from_db()
    return scan


def _disposition(scan: SecurityScan, severity: str) -> str:
    if (
        scan.blocking_enabled
        and SEVERITY_RANK[severity] >= SEVERITY_RANK[scan.blocking_severity]
    ):
        return SecurityDisposition.BLOCKING
    if SEVERITY_RANK[severity] >= SEVERITY_RANK[SecuritySeverity.MEDIUM]:
        return SecurityDisposition.WARNING
    return SecurityDisposition.INFORMATIONAL


def _segment_finding(
    scan: SecurityScan,
    segment: ScanSegment,
    detection: SecurityDetection,
) -> SecurityFinding | None:
    lookup = {
        "scan": scan,
        "resource_type": segment.resource_type,
        "resource_id": segment.resource_id,
        "location": segment.location,
        "check_key": detection.check,
        "category": detection.category,
    }
    finding, created = SecurityFinding.objects.get_or_create(
        **lookup,
        defaults={
            "project": scan.project,
            "title": detection.title[:240],
            "description": detection.description,
            "severity": detection.severity,
            "disposition": _disposition(scan, detection.severity),
            "classification": SecurityClassification.RISK,
            "resource_label": segment.resource_label[:240],
            "evidence": detection.evidence[:4000],
            "remediation": detection.remediation,
            "rule_id": detection.rule_id[:120],
            "execution": segment.execution,
            "execution_result": segment.execution_result,
            "metadata": detection.metadata,
        },
    )
    if created:
        SecurityFindingEvent.objects.create(
            finding=finding,
            from_status="",
            to_status=SecurityFinding.Status.OPEN,
            note="Detected by security scan.",
            actor=scan.created_by,
        )
    return finding if created else None


def _summary(scan: SecurityScan, *, truncated: bool) -> dict:
    findings = SecurityFinding.objects.filter(scan=scan)
    severity = {
        row["severity"]: row["count"]
        for row in findings.values("severity").annotate(count=Count("id"))
    }
    categories = [
        {"category": row["category"], "count": row["count"]}
        for row in findings.values("category")
        .annotate(count=Count("id"))
        .order_by("-count", "category")
    ]
    status = {
        row["status"]: row["count"]
        for row in findings.values("status").annotate(count=Count("id"))
    }
    disposition = {
        row["disposition"]: row["count"]
        for row in findings.values("disposition").annotate(count=Count("id"))
    }
    highest = ""
    for value in SEVERITY_ORDER:
        if severity.get(value):
            highest = value
    return {
        "checks": list(scan.checks or []),
        "target": {
            "type": scan.target_type,
            "label": scan.target_label,
            "version": scan.target_version,
            "identifier": scan.target_identifier,
        },
        "severity_counts": severity,
        "category_counts": categories,
        "status_counts": status,
        "disposition_counts": disposition,
        "highest_severity": highest,
        "truncated": truncated,
        "limitations": [
            registry.CHECKS[key].limitation
            for key in scan.checks or []
            if key in registry.CHECKS
        ],
    }


def _scan_target(scan: SecurityScan):
    target = getattr(scan, scan.target_type, None)
    if target is None:
        raise ValidationError(
            {"target": "The scan target no longer exists; start a new scan."}
        )
    return target


def execute_scan(*, scan_id, task_id: str = "") -> dict:
    """Execute a queued scan and persist findings. Safe to inspect after failure."""
    scan = (
        SecurityScan.objects.select_related(
            "project", "dataset", "prompt", "execution"
        )
        .filter(pk=scan_id)
        .first()
    )
    if scan is None:
        return {"scan": str(scan_id), "status": "missing"}
    if scan.status in TERMINAL_STATUSES:
        return {"scan": str(scan.pk), "status": scan.status}

    scan.status = SecurityScan.Status.RUNNING
    scan.started_at = timezone.now()
    scan.error = None
    if task_id:
        scan.task_id = str(task_id)[:200]
    scan.save(update_fields=["status", "started_at", "error", "task_id"])

    truncated = False
    try:
        target = _scan_target(scan)
        segments, truncated = collect_segments(scan.target_type, target)
        scan.total_items = len(segments)
        scan.scanned_items = 0
        scan.save(update_fields=["total_items", "scanned_items"])
        checked = 0
        for index, segment in enumerate(segments, start=1):
            detections = registry.run(
                segment.text,
                checks=scan.checks or [],
                segment_kind=segment.kind,
                pii_categories=(scan.config or {}).get("pii_categories"),
            )
            for detection in detections:
                _segment_finding(scan, segment, detection)
            checked += 1
            if index == len(segments) or index % 10 == 0:
                SecurityScan.objects.filter(pk=scan.pk).update(
                    scanned_items=checked,
                    finding_count=SecurityFinding.objects.filter(scan=scan).count(),
                )
        scan.refresh_from_db()
        scan.summary = _summary(scan, truncated=truncated)
        scan.finding_count = SecurityFinding.objects.filter(scan=scan).count()
        scan.highest_severity = scan.summary["highest_severity"]
        scan.status = SecurityScan.Status.COMPLETED
        scan.completed_at = timezone.now()
        scan.save(
            update_fields=[
                "summary",
                "finding_count",
                "highest_severity",
                "status",
                "completed_at",
            ]
        )
    except Exception:  # noqa: BLE001 - the scan must reach a terminal state
        logger.exception("Security scan %s failed", scan.pk)
        _mark_failed(
            scan,
            "scan_error",
            "The security scan stopped unexpectedly. Start a new scan to retry.",
        )
    scan.refresh_from_db()
    return {"scan": str(scan.pk), "status": scan.status}


@transaction.atomic
def rerun_scan(*, actor, scan_id) -> SecurityScan:
    source = scan_for_user(actor, scan_id, Membership.Role.MEMBER)
    target = _scan_target(source)
    new_scan = create_scan(
        actor=actor,
        project_id=source.project_id,
        validated_data={
            "target_type": source.target_type,
            "target_id": target.pk,
            "checks": source.checks,
            "config": source.config,
            "blocking_enabled": source.blocking_enabled,
            "blocking_severity": source.blocking_severity,
            "blocking_reason": source.blocking_reason,
        },
    )
    return enqueue_scan(new_scan)


def dashboard(*, user, project_id) -> dict:
    project = _project(user, project_id)
    scans = SecurityScan.objects.filter(project=project)
    findings = SecurityFinding.objects.filter(project=project)
    test_runs = SecurityTestRun.objects.filter(project=project)
    test_results = SecurityTestResult.objects.filter(run__project=project).exclude(
        status=SecurityTestResult.Status.PENDING
    )
    severity_counts = {
        row["severity"]: row["count"]
        for row in findings.values("severity").annotate(count=Count("id"))
    }
    status_counts = {
        row["status"]: row["count"]
        for row in findings.values("status").annotate(count=Count("id"))
    }
    disposition_counts = {
        row["disposition"]: row["count"]
        for row in findings.values("disposition").annotate(count=Count("id"))
    }
    categories = [
        {"category": row["category"], "count": row["count"]}
        for row in findings.values("category")
        .annotate(count=Count("id"))
        .order_by("-count", "category")
    ]
    recent_scans = list(
        scans.select_related("created_by", "dataset", "prompt", "execution")[:10]
    )
    recent_findings = list(
        findings.select_related("scan", "reviewed_by")
        .prefetch_related("events__actor")
        .order_by("-detected_at")[:10]
    )
    return {
        "project": str(project.pk),
        "scans": scans.count(),
        "completed_scans": scans.filter(
            status=SecurityScan.Status.COMPLETED
        ).count(),
        "running_scans": scans.filter(
            status__in=[SecurityScan.Status.QUEUED, SecurityScan.Status.RUNNING]
        ).count(),
        "findings": findings.count(),
        "open_findings": findings.filter(
            status=SecurityFinding.Status.OPEN
        ).count(),
        "reviewed_findings": findings.filter(
            status=SecurityFinding.Status.REVIEWED
        ).count(),
        "resolved_findings": findings.filter(
            status=SecurityFinding.Status.RESOLVED
        ).count(),
        "blocking_findings": findings.filter(
            disposition=SecurityDisposition.BLOCKING
        ).count(),
        "security_test_runs": test_runs.count(),
        "security_tests": test_results.count(),
        "security_tests_failed": test_results.filter(
            verdict=SecurityTestResult.Verdict.FAILED
        ).count(),
        "security_test_runs_running": test_runs.filter(
            status__in=[
                SecurityTestRun.Status.QUEUED,
                SecurityTestRun.Status.RUNNING,
            ]
        ).count(),
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "disposition_counts": disposition_counts,
        "categories": categories,
        "recent_scans": recent_scans,
        "recent_findings": recent_findings,
        "disclaimer": (
            "Security checks are detection aids, not a guarantee that the "
            "system is secure. Findings can be false positives or miss issues; "
            "review each result in context."
        ),
    }


@transaction.atomic
def update_finding(*, actor, finding_id, validated_data) -> SecurityFinding:
    finding = finding_for_user(actor, finding_id, Membership.Role.MEMBER)
    old_status = finding.status
    new_status = validated_data.get("status", finding.status)
    if new_status not in STATUSES:
        raise ValidationError({"status": "Unknown review status."})
    note = str(validated_data.get("note") or "").strip()
    classification = validated_data.get("classification")
    if classification and classification not in SecurityClassification.values:
        raise ValidationError({"classification": "Unknown finding classification."})

    if classification and classification != finding.classification:
        finding.classification = classification
    if new_status != old_status:
        finding.status = new_status
        if new_status in (
            SecurityFinding.Status.REVIEWED,
            SecurityFinding.Status.RESOLVED,
        ):
            finding.reviewed_by = actor
            finding.reviewed_at = timezone.now()
        if new_status == SecurityFinding.Status.RESOLVED:
            finding.resolved_at = timezone.now()
        elif new_status == SecurityFinding.Status.OPEN:
            finding.resolved_at = None
        if note:
            finding.resolution_note = note[:2000]
        finding.save(
            update_fields=[
                "classification",
                "status",
                "reviewed_by",
                "reviewed_at",
                "resolved_at",
                "resolution_note",
                "updated_at",
            ]
        )
        SecurityFindingEvent.objects.create(
            finding=finding,
            from_status=old_status,
            to_status=new_status,
            note=note,
            actor=actor,
        )
    elif classification and classification != finding.classification:
        finding.save(update_fields=["classification", "updated_at"])
        SecurityFindingEvent.objects.create(
            finding=finding,
            from_status=old_status,
            to_status=old_status,
            note=note or f"Classification changed to {classification}.",
            actor=actor,
        )
    elif note:
        finding.resolution_note = note[:2000]
        finding.save(update_fields=["resolution_note", "updated_at"])

    return finding_for_user(actor, finding.pk)
