"""Shared detector types and evidence redaction helpers.

Detectors return potential risks, not confirmed vulnerabilities.  They must never
put a raw sensitive match into a finding: callers persist only the redacted
``evidence`` produced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITY_INFO = "info"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

SEVERITIES = (
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
)
SEVERITY_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}


@dataclass(frozen=True)
class SecurityDetection:
    """One potential security issue found in one piece of text."""

    check: str
    category: str
    title: str
    description: str
    severity: str
    remediation: str
    rule_id: str
    evidence: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionRule:
    """A detector rule; new rules can be registered without changing the scanner."""

    code: str
    category: str
    title: str
    description: str
    severity: str
    remediation: str
    patterns: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def redact_excerpt(
    text: str,
    start: int,
    end: int,
    label: str,
    *,
    window: int = 80,
    limit: int = 300,
) -> str:
    """Return a short context window with the matched value replaced.

    The raw match is deliberately excluded.  Callers that handle PII must also
    scrub any other matching values in the surrounding context before persisting.
    """
    prefix = text[max(0, start - window) : start]
    suffix = text[end : min(len(text), end + window)]
    excerpt = f"{prefix}[REDACTED:{label.upper()}]{suffix}"
    return " ".join(excerpt.split())[:limit]
