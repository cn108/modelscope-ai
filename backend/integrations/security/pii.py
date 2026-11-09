"""Configurable personally identifiable information (PII) detectors.

The patterns are intentionally conservative and deterministic.  They are not a
complete PII classifier, so findings are potential risks and always require
human review.  Only redacted evidence leaves this module.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from .base import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SecurityDetection,
    redact_excerpt,
)

EMAIL = "email"
PHONE = "phone"
SSN = "ssn"
CREDIT_CARD = "credit_card"
IP_ADDRESS = "ip_address"

PII_CATEGORIES = (EMAIL, PHONE, SSN, CREDIT_CARD, IP_ADDRESS)


@dataclass(frozen=True)
class PIICategory:
    key: str
    label: str
    severity: str
    description: str
    remediation: str
    pattern: re.Pattern


_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+(?![\w-])(?!\.\w)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?<![\w+])(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)"
)
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_CARD_RE = re.compile(r"(?<!\w)(?:\d[ -]?){13,19}(?!\w)")
_IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w])(?!\.\d)")
_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])", re.I)

SPECS = {
    EMAIL: PIICategory(
        key=EMAIL,
        label="Email address",
        severity=SEVERITY_LOW,
        description="A value resembling an email address was detected.",
        remediation=(
            "Remove or tokenise the email address before sharing the prompt, "
            "dataset or response, and verify the source data retention policy."
        ),
        pattern=_EMAIL_RE,
    ),
    PHONE: PIICategory(
        key=PHONE,
        label="Telephone number",
        severity=SEVERITY_MEDIUM,
        description="A value resembling a telephone number was detected.",
        remediation=(
            "Redact the number, confirm whether the data subject consented to "
            "its use, and avoid sending it to external model providers."
        ),
        pattern=_PHONE_RE,
    ),
    SSN: PIICategory(
        key=SSN,
        label="Government identification number",
        severity=SEVERITY_HIGH,
        description="A value resembling a US Social Security number was detected.",
        remediation=(
            "Treat the value as highly sensitive: remove it, rotate any exposed "
            "credential or identifier, and review access to the source record."
        ),
        pattern=_SSN_RE,
    ),
    CREDIT_CARD: PIICategory(
        key=CREDIT_CARD,
        label="Payment card number",
        severity=SEVERITY_HIGH,
        description="A digit sequence that passes a payment-card checksum was detected.",
        remediation=(
            "Never store or transmit the full card number. Tokenise it through "
            "the payment processor and remove it from prompts and datasets."
        ),
        pattern=_CARD_RE,
    ),
    IP_ADDRESS: PIICategory(
        key=IP_ADDRESS,
        label="IP address",
        severity=SEVERITY_LOW,
        description="A value resembling an IPv4 or IPv6 address was detected.",
        remediation=(
            "Decide whether the address is personal data in your jurisdiction; "
            "redact it or replace it with a stable pseudonym where possible."
        ),
        pattern=_IPV4_RE,
    ),
}


def available_categories() -> list[dict]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "severity": spec.severity,
            "description": spec.description,
        }
        for spec in SPECS.values()
    ]


def normalize_categories(categories=None) -> tuple[str, ...]:
    if categories in (None, []):
        return PII_CATEGORIES
    values = tuple(
        dict.fromkeys(str(value).strip() for value in categories if str(value).strip())
    )
    unknown = [value for value in values if value not in SPECS]
    if unknown:
        raise ValueError(
            "Unknown PII categories: " + ", ".join(sorted(unknown))
        )
    return values or PII_CATEGORIES


def _luhn(value: str) -> bool:
    digits = [int(character) for character in re.sub(r"\D", "", value)]
    if not 12 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _matches(spec: PIICategory, text: str):
    for match in spec.pattern.finditer(text):
        value = match.group(0).strip()
        if not value:
            continue
        if spec.key == CREDIT_CARD and not _luhn(value):
            continue
        if spec.key == IP_ADDRESS and not _is_ip(value):
            continue
        yield match


def scrub_pii(text: str) -> str:
    """Mask PII in a context window before it becomes evidence."""
    text = _EMAIL_RE.sub("[REDACTED]", text)
    text = _SSN_RE.sub("[REDACTED]", text)
    text = _CARD_RE.sub("[REDACTED]", text)
    text = _PHONE_RE.sub("[REDACTED]", text)
    text = _IPV4_RE.sub("[REDACTED]", text)
    text = _IPV6_RE.sub("[REDACTED]", text)
    return text


def detect(text: str, *, categories=None) -> list[SecurityDetection]:
    """Find one potential finding per configured PII category in *text*."""
    selected = normalize_categories(categories)
    detections: list[SecurityDetection] = []
    for key in selected:
        spec = SPECS[key]
        matches = list(_matches(spec, text))
        if not matches:
            continue
        first = matches[0]
        evidence = scrub_pii(
            redact_excerpt(text, first.start(), first.end(), spec.label)
        )
        count = len(matches)
        detections.append(
            SecurityDetection(
                check="pii",
                category=f"pii.{key}",
                title=f"Potential {spec.label.lower()} detected",
                description=(
                    f"{spec.description} This is a pattern match, not a confirmed "
                    "data-protection incident."
                ),
                severity=spec.severity,
                remediation=spec.remediation,
                rule_id=f"pii.{key}",
                evidence=evidence,
                metadata={
                    "category": key,
                    "occurrences": count,
                    "redacted": True,
                },
            )
        )
    return detections
