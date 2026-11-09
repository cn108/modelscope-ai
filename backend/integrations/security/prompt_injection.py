"""Heuristic prompt-injection detection with a registerable rule set.

These rules flag language that *may* attempt to change model instructions or
bypass restrictions.  A match is not proof that an attack succeeded, and the
detector cannot cover every wording, encoding or multi-turn strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .base import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SecurityDetection,
    redact_excerpt,
)
from .pii import scrub_pii


@dataclass(frozen=True)
class InjectionRule:
    code: str
    category: str
    title: str
    description: str
    severity: str
    remediation: str
    patterns: tuple[str, ...]


RULES: list[InjectionRule] = [
    InjectionRule(
        code="instruction_override",
        category="prompt_injection.instruction_override",
        title="Instruction override attempt",
        description=(
            "The text asks the model to ignore, forget or replace earlier "
            "instructions. This is a potential prompt-injection attempt."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Treat the matched text as untrusted input. Keep system instructions "
            "authoritative, isolate user content, and verify the request in the "
            "application before acting on it."
        ),
        patterns=(
            r"\b(?:ignore|disregard|forget|override)\s+"
            r"(?:all\s+)?(?:of\s+)?(?:the\s+)?"
            r"(?:previous|prior|above|earlier|system)\s+"
            r"(?:instructions?|prompts?|rules?|directions?)\b",
            r"\b(?:new|updated|real)\s+instructions?\s*:",
        ),
    ),
    InjectionRule(
        code="system_prompt_extraction",
        category="prompt_injection.system_prompt_extraction",
        title="System-prompt extraction attempt",
        description=(
            "The text asks the model to reveal hidden instructions or its system "
            "prompt. This may be an attempt to exfiltrate guardrails."
        ),
        severity=SEVERITY_MEDIUM,
        remediation=(
            "Do not expose system prompts in responses. Add an instruction that "
            "refuses prompt-disclosure requests and test the refusal path."
        ),
        patterns=(
            r"\b(?:reveal|show|print|repeat|leak|expose|tell me)\b"
            r".{0,50}\b(?:system|developer|hidden|internal)\s+"
            r"(?:prompt|instructions?|rules?)\b",
            r"\b(?:repeat|print|show)\b.{0,40}\b(?:everything|text)\s+above\b",
        ),
    ),
    InjectionRule(
        code="role_manipulation",
        category="prompt_injection.role_manipulation",
        title="Role manipulation attempt",
        description=(
            "The text asks the model to adopt a different identity or unrestricted "
            "persona. This can be used to weaken the intended behaviour."
        ),
        severity=SEVERITY_MEDIUM,
        remediation=(
            "Keep the system identity fixed, reject persona changes that conflict "
            "with policy, and test the model with adversarial role prompts."
        ),
        patterns=(
            r"\byou\s+are\s+now\b",
            r"\b(?:act|pretend)\s+(?:as|to be)\b",
            r"\bfrom\s+now\s+on\s+you\s+are\b",
        ),
    ),
    InjectionRule(
        code="jailbreak",
        category="prompt_injection.jailbreak",
        title="Jailbreak language detected",
        description=(
            "The text contains a known jailbreak or unrestricted-mode phrase. "
            "This is a signal for review, not confirmation of a bypass."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Block or quarantine the request, log the source, and verify that "
            "safety instructions cannot be disabled by user content."
        ),
        patterns=(
            r"\b(?:jailbreak|do anything now|dan mode|developer mode|god mode)\b",
        ),
    ),
    InjectionRule(
        code="safety_bypass",
        category="prompt_injection.safety_bypass",
        title="Safety bypass attempt",
        description=(
            "The text asks the model to disable or bypass safety restrictions. "
            "This is a potential policy-evasion attempt."
        ),
        severity=SEVERITY_HIGH,
        remediation=(
            "Treat safety controls as immutable, reject bypass requests, and "
            "review the response for policy violations."
        ),
        patterns=(
            r"\b(?:bypass|disable|turn\s+off|ignore)\b"
            r".{0,40}\b(?:safety|security|guardrails?|restrictions?|filters?)\b",
        ),
    ),
    InjectionRule(
        code="instruction_replacement",
        category="prompt_injection.instruction_replacement",
        title="Suspicious instruction replacement",
        description=(
            "The text introduces replacement instructions or asks the model to "
            "follow a new instruction set."
        ),
        severity=SEVERITY_LOW,
        remediation=(
            "Keep a clear boundary between system and user instructions and review "
            "the request before allowing any tool or data access."
        ),
        patterns=(
            r"\bfollow\s+these\s+instructions?\s+instead\b",
            r"\b(?:from\s+now\s+on|starting\s+now)\b.{0,50}\b(?:do|follow|answer)\b",
        ),
    ),
]


_NEGATION_PREFIX_RE = re.compile(
    r"(?:\bnever|\bnot|\bno|\bdon't|\bdo\s+not|\bmust\s+not|\bshould\s+not|"
    r"\bcannot|\bcan't)\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)


def _is_negated(text: str, start: int) -> bool:
    """Ignore guardrails such as ``never reveal your system prompt``."""
    prefix = text[max(0, start - 40) : start]
    return bool(_NEGATION_PREFIX_RE.search(prefix))


def rules() -> list[InjectionRule]:
    """Return the currently registered rules (extensible at import time)."""
    return list(RULES)


def register_rule(rule: InjectionRule) -> None:
    """Register an additional injection rule without editing the scanner."""
    if any(existing.code == rule.code for existing in RULES):
        raise ValueError(f"An injection rule with code {rule.code!r} already exists.")
    RULES.append(rule)


def detect(text: str, *, rules_override=None) -> list[SecurityDetection]:
    selected = list(rules_override) if rules_override is not None else RULES
    detections: list[SecurityDetection] = []
    for rule in selected:
        first = None
        count = 0
        for pattern in rule.patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                if _is_negated(text, match.start()):
                    continue
                count += 1
                if first is None:
                    first = match
        if first is None:
            continue
        evidence = scrub_pii(
            redact_excerpt(text, first.start(), first.end(), "instruction")
        )
        detections.append(
            SecurityDetection(
                check="prompt_injection",
                category=rule.category,
                title=rule.title,
                description=rule.description,
                severity=rule.severity,
                remediation=rule.remediation,
                rule_id=f"prompt_injection.{rule.code}",
                evidence=evidence,
                metadata={"rule": rule.code, "occurrences": count},
            )
        )
    return detections
