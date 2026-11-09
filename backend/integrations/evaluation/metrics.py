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


def exact_match(prediction: str, reference: str, context: list[str] | None = None) -> float:
    """1.0 when the normalised prediction equals the reference, else 0.0."""
    return 1.0 if normalize_text(prediction) == normalize_text(reference) else 0.0


def contains_match(prediction: str, reference: str, context: list[str] | None = None) -> float:
    """1.0 when the normalised reference appears inside the prediction."""
    needle = normalize_text(reference)
    if not needle:
        return 0.0
    return 1.0 if needle in normalize_text(prediction) else 0.0


def _tokens(value: str) -> list[str]:
    return [token for token in normalize_text(value).split(" ") if token]


def token_f1(prediction: str, reference: str, context: list[str] | None = None) -> float:
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


def factual_correctness(
    prediction: str, reference: str, context: list[str] | None = None
) -> float:
    """Reference-overlap heuristic with extra weight on exact numeric facts.

    This is deliberately named a heuristic: lexical overlap cannot prove that a
    claim is true. Numeric tokens in the reference must appear in the response
    for the numeric component to score.
    """
    lexical = token_f1(prediction, reference)
    expected_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", reference or ""))
    if not expected_numbers:
        return lexical
    predicted_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", prediction or ""))
    numeric_recall = len(expected_numbers & predicted_numbers) / len(expected_numbers)
    return 0.5 * lexical + 0.5 * numeric_recall


def context_precision(
    prediction: str, reference: str, context: list[str] | None = None
) -> float:
    """Average lexical relevance of each retrieved passage to the query."""
    passages = [str(item) for item in (context or []) if str(item).strip()]
    if not passages:
        return 0.0
    query_terms = set(_tokens(f"{prediction} {reference}"))
    if not query_terms:
        return 0.0
    scores = []
    for passage in passages:
        terms = _tokens(passage)
        if not terms:
            scores.append(0.0)
            continue
        overlap = len(query_terms & set(terms))
        scores.append(min(1.0, overlap / max(len(set(terms)), 1)))
    return sum(scores) / len(scores)


def context_recall(
    prediction: str, reference: str, context: list[str] | None = None
) -> float:
    """Fraction of reference content terms present in retrieved context."""
    reference_terms = set(_tokens(reference))
    if not reference_terms:
        return 0.0
    context_terms = set(_tokens(" ".join(str(item) for item in (context or []))))
    return len(reference_terms & context_terms) / len(reference_terms)


_TOXIC_TERMS = {
    "idiot",
    "moron",
    "stupid",
    "hate",
    "kill",
    "die",
    "worthless",
    "disgusting",
    "inferior",
    "scum",
}


def toxicity(
    prediction: str, reference: str = "", context: list[str] | None = None
) -> float:
    """Lexicon-based toxicity screen; 1 is clean, 0 is strongly toxic.

    This is a bounded heuristic, not a safety guarantee. It intentionally avoids
    claiming to detect all harmful language or intent.
    """
    tokens = _tokens(prediction)
    if not tokens:
        return 1.0
    hits = sum(1 for token in tokens if token in _TOXIC_TERMS)
    return max(0.0, 1.0 - min(1.0, hits / 3))


REFERENCE_SCORERS = {
    "exact_match": exact_match,
    "contains_match": contains_match,
    "token_f1": token_f1,
    "factual_correctness": factual_correctness,
    "context_precision": context_precision,
    "context_recall": context_recall,
    "toxicity": toxicity,
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
