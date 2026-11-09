"""The evaluation metric registry.

The registry is the single place that decides which metrics exist. Pages and
API clients never hardcode evaluation logic; they list this catalogue and send
metric keys when creating an evaluation run.

Only metrics that can actually execute are exposed: built-in scorers are always
available, DeepEval judge metrics appear only when the dependency is installed
and the platform setting allows them.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from rest_framework.exceptions import ValidationError

from integrations.evaluation.metrics import REFERENCE_SCORERS, judge_score

JUDGE_THRESHOLD = 0.5
MAX_METRICS_PER_RUN = 6
CUSTOM_METRICS: dict[str, "MetricDefinition"] = {}


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    description: str
    requires_expected_output: bool = False
    requires_context: bool = False
    requires_judge: bool = False
    threshold: float | None = None
    source: str = "builtin"
    version: str = "1.0"
    scorer: Callable[..., float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "requires_expected_output": self.requires_expected_output,
            "requires_context": self.requires_context,
            "requires_judge": self.requires_judge,
            "threshold": self.threshold,
            "source": self.source,
            "version": self.version,
        }


BUILTIN_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="exact_match",
        label="Exact match",
        description="Scores 1 when the response equals the expected answer after normalisation.",
        requires_expected_output=True,
        scorer=REFERENCE_SCORERS["exact_match"],
    ),
    MetricDefinition(
        key="contains_match",
        label="Contains expected answer",
        description="Scores 1 when the expected answer appears inside the response.",
        requires_expected_output=True,
        scorer=REFERENCE_SCORERS["contains_match"],
    ),
    MetricDefinition(
        key="token_f1",
        label="Token F1",
        description="Word-overlap F1 between the response and the expected answer.",
        requires_expected_output=True,
        scorer=REFERENCE_SCORERS["token_f1"],
    ),
    MetricDefinition(
        key="factual_correctness",
        label="Factual correctness (reference)",
        description=(
            "Reference-overlap heuristic with extra weight on exact numbers. "
            "It measures agreement, not verified truth."
        ),
        requires_expected_output=True,
        threshold=0.5,
        scorer=REFERENCE_SCORERS["factual_correctness"],
    ),
    MetricDefinition(
        key="context_precision",
        label="Context precision",
        description="Average lexical relevance of retrieved context to the query.",
        requires_context=True,
        threshold=0.5,
        scorer=REFERENCE_SCORERS["context_precision"],
    ),
    MetricDefinition(
        key="context_recall",
        label="Context recall",
        description="Fraction of expected-answer terms found in retrieved context.",
        requires_expected_output=True,
        requires_context=True,
        threshold=0.5,
        scorer=REFERENCE_SCORERS["context_recall"],
    ),
    MetricDefinition(
        key="toxicity",
        label="Toxicity screen",
        description=(
            "Lexicon-based screen; 1 is clean and 0 is strongly toxic. "
            "Not a safety guarantee."
        ),
        threshold=0.8,
        scorer=REFERENCE_SCORERS["toxicity"],
    ),
)

JUDGE_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="answer_relevancy",
        label="Answer relevancy",
        description="DeepEval judge: how directly the response addresses the input.",
        requires_judge=True,
        threshold=JUDGE_THRESHOLD,
        source="deepeval",
    ),
    MetricDefinition(
        key="faithfulness",
        label="Faithfulness",
        description="DeepEval judge: whether claims in the response are supported by the record context.",
        requires_context=True,
        requires_judge=True,
        threshold=JUDGE_THRESHOLD,
        source="deepeval",
    ),
    MetricDefinition(
        key="contextual_relevancy",
        label="Contextual relevancy",
        description="DeepEval judge: how much of the record context is relevant to the input.",
        requires_context=True,
        requires_judge=True,
        threshold=JUDGE_THRESHOLD,
        source="deepeval",
    ),
)


def judge_metrics_available() -> bool:
    """True only when DeepEval is importable and the platform enables judges."""
    if not getattr(settings, "EVALUATION_JUDGE_METRICS_ENABLED", True):
        return False
    return importlib.util.find_spec("deepeval") is not None


def register_metric(definition: MetricDefinition) -> None:
    """Register a custom evaluator without changing orchestration code.

    Custom metrics run in-process with the same contract as built-ins. Only
    trusted deployment code should call this; there is intentionally no HTTP
    endpoint that accepts executable metric code.
    """
    if definition.requires_judge or definition.scorer is None:
        raise ValueError("Custom metrics need an in-process scorer and no judge.")
    if not definition.key or definition.key in {item.key for item in definitions()}:
        raise ValueError("A metric with this key already exists.")
    CUSTOM_METRICS[definition.key] = definition


def unregister_metric(key: str) -> None:
    CUSTOM_METRICS.pop(key, None)


def definitions() -> tuple[MetricDefinition, ...]:
    base = BUILTIN_METRICS + tuple(CUSTOM_METRICS.values())
    if judge_metrics_available():
        return base + JUDGE_METRICS
    return base


def catalog() -> list[dict[str, Any]]:
    return [definition.as_dict() for definition in definitions()]


def registry() -> dict[str, MetricDefinition]:
    return {definition.key: definition for definition in definitions()}


def resolve_metrics(keys: list[str]) -> list[MetricDefinition]:
    """Validate requested metric keys against the registry."""
    if not keys:
        raise ValidationError({"metrics": "Select at least one metric."})
    if len(keys) > MAX_METRICS_PER_RUN:
        raise ValidationError(
            {"metrics": f"Select at most {MAX_METRICS_PER_RUN} metrics per evaluation."}
        )
    known = registry()
    resolved: list[MetricDefinition] = []
    seen: set[str] = set()
    for key in keys:
        cleaned = str(key).strip()
        if cleaned in seen:
            continue
        definition = known.get(cleaned)
        if definition is None:
            raise ValidationError(
                {"metrics": f"Metric '{cleaned}' is not available on this platform."}
            )
        seen.add(cleaned)
        resolved.append(definition)
    return resolved


def evaluate(
    definition: MetricDefinition,
    *,
    case: dict[str, Any],
    judge: Any | None,
) -> dict[str, Any]:
    """Compute one metric for one case, capturing errors per metric."""
    result: dict[str, Any] = {
        "metric": definition.key,
        "label": definition.label,
        "score": None,
        "passed": None,
        "threshold": definition.threshold,
        "metric_version": definition.version,
        "reason": "",
        "error": None,
    }
    if definition.requires_expected_output and not (case.get("expected_output") or "").strip():
        result["error"] = "This metric needs an expected answer on the dataset record."
        return result
    if definition.requires_context and not case.get("context"):
        result["error"] = "This metric needs retrieval context on the dataset record."
        return result
    if definition.requires_judge and judge is None:
        result["error"] = "This metric needs a judge model."
        return result

    try:
        if definition.requires_judge:
            outcome = judge_score(
                definition.key,
                case=case,
                judge=judge,
                threshold=definition.threshold or JUDGE_THRESHOLD,
            )
            result.update(outcome)
        else:
            scorer = definition.scorer
            assert scorer is not None  # registry validation prevents this
            score = scorer(
                case.get("actual_output") or "",
                case.get("expected_output") or "",
                case.get("context") or [],
            )
            threshold = definition.threshold if definition.threshold is not None else 1.0
            result["score"] = float(score)
            result["passed"] = bool(score >= threshold)
    except Exception as exc:  # noqa: BLE001 - a judge failure is data, not a crash
        message = str(exc).strip() or "The metric could not be computed."
        result["error"] = message[:400]
    return result
