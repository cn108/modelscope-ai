"""Heuristic unsafe-output checks for model responses.

These are policy-risk signals, not content-safety guarantees.  They cannot
determine intent, context or whether content is actually harmful, and false
positives/negatives are expected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SecurityDetection,
    redact_excerpt,
)
from .pii import scrub_pii


@dataclass(frozen=True)
class OutputRule:
    code: str
    category: str
    title: str
    description: str
    severity: str
    remediation: str
    patterns: tuple[str, ...]


RULES: list[OutputRule] = [
    OutputRule(
        code="self_harm",
        category="unsafe_output.self_harm",
        title="Potential self-harm content",
        description=(
            "The response contains language associated with self-harm or suicide. "
            "This is a potential policy risk and requires human review."
        ),
        severity=SEVERITY_CRITICAL,
        remediation=(
            "Quarantine the response, add crisis-support guidance, and escalate "
            "to the appropriate safety process. Do not present the response as safe."
        ),
        patterns=(
            r"\b(?:kill\s+yourself|how\s+to\s+(?:commit\s+)?suicide|"
            r"suicide\s+(?:method|instructions)|self[- ]harm\s+(?:method|instructions))\b",
        ),
    ),
    OutputRule(
        code="violence",
        category="unsafe_output.violence",
        title="Potential violent or weapons content",
        description=(
            "The response contains language about making weapons or causing "
            "serious harm. This is a potential policy risk, not a confirmed intent."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Review the response and its context, apply the platform safety policy, "
            "and remove operational detail from any user-facing surface."
        ),
        patterns=(
            r"\b(?:how\s+to\s+(?:make|build)\s+(?:a\s+)?bomb|"
            r"(?:make|build)\s+(?:a\s+)?bomb|shoot\s+up|"
            r"how\s+to\s+kill\s+(?:someone|people)|mass\s+shooting)\b",
        ),
    ),
    OutputRule(
        code="hate",
        category="unsafe_output.hate",
        title="Potential hateful content",
        description=(
            "The response contains language associated with hateful or dehumanising "
            "content. This is a potential policy risk requiring human review."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Quarantine the response, review it against the hate-speech policy, and "
            "record the decision without treating the detector as authoritative."
        ),
        patterns=(
            r"\b(?:hate\s+(?:all|every)|inferior\s+race|"
            r"genocide\s+(?:instructions|guide)|ethnic\s+cleansing)\b",
        ),
    ),
    OutputRule(
        code="illegal_activity",
        category="unsafe_output.illegal_activity",
        title="Potential illegal-activity instructions",
        description=(
            "The response appears to provide instructions for illegal activity. "
            "This is a potential policy risk and requires human review."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Do not execute or redistribute the instructions. Review the response "
            "against applicable law and platform policy, and remove actionable detail."
        ),
        patterns=(
            r"\b(?:make\s+meth|manufacture\s+meth|launder\s+money|"
            r"how\s+to\s+hack|steal\s+(?:a\s+)?credit\s+card)\b",
        ),
    ),
    OutputRule(
        code="sexual_content",
        category="unsafe_output.sexual_content",
        title="Potential sexual content",
        description=(
            "The response contains explicitly sexual language. This is a potential "
            "policy risk; context and age-safety requirements must be reviewed."
        ),
        severity=SEVERITY_MEDIUM,
        remediation=(
            "Review the response against the content policy and age restrictions, "
            "and redact or reject it where appropriate."
        ),
        patterns=(
            r"\b(?:explicit\s+sexual|pornographic|"
            r"sexual\s+content\s+involving\s+minors)\b",
        ),
    ),
    OutputRule(
        code="credential_exposure",
        category="unsafe_output.credential_exposure",
        title="Potential credential exposure",
        description=(
            "The response appears to expose a password, API key or secret. Treat "
            "the credential as compromised until verified."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Rotate the exposed credential, remove it from logs and responses, and "
            "review how the secret entered the model context."
        ),
        patterns=(
            r"\b(?:here\s+(?:is|are)\s+(?:the\s+)?(?:password|api\s+key|secret)|"
            r"api[_ -]?key\s*[:=])",
        ),
    ),
]


def rules() -> list[OutputRule]:
    return list(RULES)


def register_rule(rule: OutputRule) -> None:
    if any(existing.code == rule.code for existing in RULES):
        raise ValueError(f"An output rule with code {rule.code!r} already exists.")
    RULES.append(rule)


def detect(text: str, *, rules_override=None) -> list[SecurityDetection]:
    selected = list(rules_override) if rules_override is not None else RULES
    detections: list[SecurityDetection] = []
    for rule in selected:
        first = None
        count = 0
        for pattern in rule.patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                count += 1
                if first is None:
                    first = match
        if first is None:
            continue
        evidence = scrub_pii(
            redact_excerpt(text, first.start(), first.end(), "content")
        )
        if rule.code == "credential_exposure":
            # The matched credential label is redacted, but its value follows
            # immediately after the match and must never be stored as evidence.
            evidence = re.sub(
                r"\[REDACTED:CONTENT\](?::\s*)?\S*",
                "[REDACTED:CREDENTIAL]",
                evidence,
            )
        detections.append(
            SecurityDetection(
                check="unsafe_output",
                category=rule.category,
                title=rule.title,
                description=rule.description,
                severity=rule.severity,
                remediation=rule.remediation,
                rule_id=f"unsafe_output.{rule.code}",
                evidence=evidence,
                metadata={"rule": rule.code, "occurrences": count},
            )
        )
    return detections
