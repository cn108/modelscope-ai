"""Extensible catalog for controlled AI security test cases."""

from __future__ import annotations

import secrets

from .base import AttackCase, RenderedCase
from .cases import CASES, CASES_BY_KEY, CATEGORY_LABELS, CATEGORY_ORDER
from .detectors import DETECTORS


def canary_token() -> str:
    return f"MSSEC-{secrets.token_hex(6).upper()}"


def render_case(case: AttackCase, canary: str) -> RenderedCase:
    email = f"security-canary-{canary.lower()}@example.invalid"
    number = int(secrets.token_hex(2), 16) % 10000
    prefix = int(secrets.token_hex(1), 16) % 1000
    phone = f"+1 555 {prefix:03d} {number:04d}"
    replacements = {
        "{canary}": canary,
        "{canary_email}": email,
        "{canary_phone}": phone,
    }
    system_prompt = case.system_prompt
    prompt = case.prompt
    for placeholder, value in replacements.items():
        system_prompt = system_prompt.replace(placeholder, value)
        prompt = prompt.replace(placeholder, value)
    config = dict(case.detector_config)
    if case.detector == "pii_disclosure":
        config.update({"email": email, "phone": phone})
    return RenderedCase(
        key=case.key,
        category=case.category,
        category_label=case.category_label,
        name=case.name,
        description=case.description,
        technique=case.technique,
        severity=case.severity,
        system_prompt=system_prompt,
        prompt=prompt,
        detector=case.detector,
        detector_config=config,
        criteria=case.criteria,
        mitigation=case.mitigation,
        references=case.references,
        limitation=case.limitation,
        canary=canary,
    )


def register_case(case: AttackCase) -> None:
    """Register an additional reviewed case without changing the runner."""
    if case.key in CASES_BY_KEY:
        raise ValueError(f"A security test case with key {case.key!r} already exists.")
    if case.category not in CATEGORY_LABELS:
        raise ValueError(f"Unknown attack category {case.category!r}.")
    if case.detector not in DETECTORS:
        raise ValueError(f"Unknown detector {case.detector!r}.")
    CASES_BY_KEY[case.key] = case
    CASES.append(case)


def validate_cases(keys) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(str(key).strip() for key in (keys or []) if str(key).strip())
    )
    if not values:
        raise ValueError("Select at least one security test case.")
    unknown = [key for key in values if key not in CASES_BY_KEY]
    if unknown:
        raise ValueError("Unknown security test cases: " + ", ".join(sorted(unknown)))
    return values


def validate_categories(categories) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(
            str(category).strip()
            for category in (categories or [])
            if str(category).strip()
        )
    )
    unknown = [value for value in values if value not in CATEGORY_LABELS]
    if unknown:
        raise ValueError("Unknown attack categories: " + ", ".join(sorted(unknown)))
    return values


def cases_for_categories(categories) -> tuple[str, ...]:
    selected = set(validate_categories(categories))
    return tuple(case.key for case in CASES if case.category in selected)


def catalog() -> dict:
    categories = []
    for key in CATEGORY_ORDER:
        items = [case for case in CASES if case.category == key]
        categories.append(
            {
                "key": key,
                "label": CATEGORY_LABELS[key],
                "count": len(items),
                "cases": [
                    {
                        "key": case.key,
                        "name": case.name,
                        "description": case.description,
                        "technique": case.technique,
                        "severity": case.severity,
                        "criteria": case.criteria,
                        "limitation": case.limitation,
                        "references": list(case.references),
                    }
                    for case in items
                ],
            }
        )
    return {
        "categories": categories,
        "case_count": len(CASES),
        "detectors": sorted(DETECTORS),
        "disclaimer": (
            "Automated security testing is a detection aid. A pass does not prove a "
            "model is secure, and an inconclusive result is not a pass. Cases are "
            "single-turn probes against models configured in this project."
        ),
        "limitations": [
            "Only reviewed, fixed attack cases are sent; arbitrary prompts and external "
            "targets are not accepted.",
            "Deterministic detectors can miss paraphrased, encoded or multi-turn attacks.",
            "A failed case is evidence of the observed response, not proof that every "
            "deployment of the model is vulnerable.",
            "Model behaviour can change with provider updates, parameters and system "
            "context; rerun the same cases before and after changes.",
        ],
    }


def seeds() -> tuple[AttackCase, ...]:
    return CASES
