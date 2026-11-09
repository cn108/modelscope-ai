"""Audit event creation shared by domain services (§11)."""

from common.audit.models import AuditEvent


def record_event(
    *,
    actor,
    action: str,
    workspace=None,
    target_type: str = "",
    target_id=None,
    metadata: dict | None = None,
) -> AuditEvent:
    if not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        workspace=workspace,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )
