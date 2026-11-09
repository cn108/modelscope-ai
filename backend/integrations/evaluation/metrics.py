"""Metric implementations behind the evaluation registry.

Two families exist:

- ``reference`` metrics are deterministic comparisons against a record's
  ``expected_output``. They need no model and always produce a score in [0, 1].
- ``judge`` metrics delegate to DeepEval, using a provider/model supplied by the
  caller as the judge. They are only registered when DeepEval is installed.

Scores are normalised to 0..1 and ``passed`` means ``score >= threshold``.
"""

from __future__ import annotations

import re
from typing import Any

_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for comparison."""
    text = (value or "").strip().lower()
    text = _PUNCTUATION.sub(" ", text)
    text = _ARTICLES.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def exact_match(prediction: str, reference: str) -> float:
    """1.0 when the normalised prediction equals the reference, else 0.0."""
    return 1.0 if normalize_text(prediction) == normalize_text(reference) else 0.0


def contains_match(prediction: str, reference: str) -> float:
    """1.0 when the normalised reference appears inside the prediction."""
    needle = normalize_text(reference)
    if not needle:
        return 0.0
    return 1.0 if needle in normalize_text(prediction) else 0.0


def _tokens(value: str) -> list[str]:
    return [token for token in normalize_text(value).split(" ") if token]


def token_f1(prediction: str, reference: str) -> float:
    """Token-overlap F1 (SQuAD style), ignoring word order."""
    predicted = _tokens(prediction)
    expected = _tokens(reference)
    if not predicted or not expected:
        return 0.0
    remaining = list(expected)
    overlap = 0
    for token in predicted:
        if token in remaining:
            remaining.remove(token)
            overlap += 1
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


REFERENCE_SCORERS = {
    "exact_match": exact_match,
    "contains_match": contains_match,
    "token_f1": token_f1,
}


def judge_score(metric_key: str, *, case: dict[str, Any], judge: Any, threshold: float) -> dict[str, Any]:
    """Run a DeepEval metric with ``judge`` as the scoring model."""
    # Imported lazily so the platform boots without the optional dependency.
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase

    classes = {
        "answer_relevancy": AnswerRelevancyMetric,
        "faithfulness": FaithfulnessMetric,
        "contextual_relevancy": ContextualRelevancyMetric,
    }
    metric_class = classes[metric_key]
    metric = metric_class(
        model=judge,
        threshold=threshold,
        include_reason=True,
        async_mode=False,
        verbose_mode=False,
    )
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=case.get("actual_output") or "",
        expected_output=case.get("expected_output") or None,
        retrieval_context=case.get("context") or None,
    )
    metric.measure(test_case)
    score = metric.score
    return {
        "score": float(score) if score is not None else None,
        "passed": bool(score is not None and score >= threshold),
        "threshold": threshold,
        "reason": (metric.reason or "")[:1000],
    }
