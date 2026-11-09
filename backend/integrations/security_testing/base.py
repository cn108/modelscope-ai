"""Types shared by the controlled AI security testing engine (M9).

The engine sends fixed, reviewed attack cases to a model that the caller has
already configured in a project.  A result is only ``failed`` when a case's
explicit detection criteria match; a response that merely looks suspicious is
``inconclusive`` rather than a confirmed vulnerability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PASSED = "passed"
FAILED = "failed"
INCONCLUSIVE = "inconclusive"
VERDICTS = (PASSED, FAILED, INCONCLUSIVE)


@dataclass(frozen=True)
class AttackCase:
    key: str
    category: str
    category_label: str
    name: str
    description: str
    technique: str
    severity: str
    system_prompt: str
    prompt: str
    detector: str
    detector_config: dict
    criteria: str
    mitigation: str
    references: tuple[str, ...] = ()
    limitation: str = ""


@dataclass(frozen=True)
class RenderedCase:
    key: str
    category: str
    category_label: str
    name: str
    description: str
    technique: str
    severity: str
    system_prompt: str
    prompt: str
    detector: str
    detector_config: dict
    criteria: str
    mitigation: str
    references: tuple[str, ...] = ()
    limitation: str = ""
    canary: str = ""


@dataclass(frozen=True)
class DetectionOutcome:
    verdict: str
    rationale: str
    evidence: str
    matched_rules: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)
