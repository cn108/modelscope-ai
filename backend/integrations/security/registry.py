"""Security check catalog and dispatch.

Adding a check means registering a `CheckDefinition` and a detector function;
the scan service, API and UI use this catalog instead of hard-coded check lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import pii, prompt_injection, unsafe_output
from .base import SecurityDetection


@dataclass(frozen=True)
class CheckDefinition:
    key: str
    label: str
    description: str
    applies_to: frozenset[str]
    detector: Callable[..., list[SecurityDetection]]
    limitation: str


CHECKS: dict[str, CheckDefinition] = {
    "pii": CheckDefinition(
        key="pii",
        label="PII detection",
        description=(
            "Find configured categories of personal data in prompts, datasets "
            "and model responses."
        ),
        applies_to=frozenset({"input", "system", "context", "output"}),
        detector=pii.detect,
        limitation=(
            "Pattern-based PII detection can miss unusual formats and can flag "
            "non-personal values. It cannot establish a data-protection breach."
        ),
    ),
    "prompt_injection": CheckDefinition(
        key="prompt_injection",
        label="Prompt injection detection",
        description=(
            "Find language that may try to override instructions, extract system "
            "prompts or bypass restrictions."
        ),
        applies_to=frozenset({"input", "system", "context"}),
        detector=prompt_injection.detect,
        limitation=(
            "Prompt injection is adversarial and context-dependent. A match is a "
            "signal for review, not proof that an attack succeeded."
        ),
    ),
    "unsafe_output": CheckDefinition(
        key="unsafe_output",
        label="Unsafe output check",
        description=(
            "Flag potentially harmful, sensitive or policy-violating model "
            "responses for human review."
        ),
        applies_to=frozenset({"output"}),
        detector=unsafe_output.detect,
        limitation=(
            "Heuristic output checks cannot guarantee safety, understand all "
            "context, or detect every harmful response. False positives and "
            "false negatives are expected."
        ),
    ),
}


def catalog() -> dict:
    return {
        "checks": [
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "applies_to": sorted(definition.applies_to),
                "limitation": definition.limitation,
            }
            for definition in CHECKS.values()
        ],
        "pii_categories": pii.available_categories(),
        "disclaimer": (
            "Security checks are detection aids, not a guarantee that a prompt, "
            "dataset, model or response is secure. Always review findings in context."
        ),
    }


def validate_checks(keys) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(str(key).strip() for key in (keys or []) if str(key).strip())
    )
    if not values:
        raise ValueError("Select at least one security check.")
    unknown = [key for key in values if key not in CHECKS]
    if unknown:
        raise ValueError("Unknown security checks: " + ", ".join(sorted(unknown)))
    return values


def applies(check: str, segment_kind: str) -> bool:
    return segment_kind in CHECKS[check].applies_to


def run(
    text: str,
    *,
    checks,
    segment_kind: str,
    pii_categories=None,
) -> list[SecurityDetection]:
    """Run selected checks against one text segment."""
    detections: list[SecurityDetection] = []
    for key in checks:
        if not applies(key, segment_kind):
            continue
        if key == "pii":
            detections.extend(
                CHECKS[key].detector(text, categories=pii_categories)
            )
        else:
            detections.extend(CHECKS[key].detector(text))
    return detections
