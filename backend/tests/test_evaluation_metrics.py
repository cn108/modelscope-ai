import pytest
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

from integrations.evaluation import registry
from integrations.evaluation.judge import JudgeError, ProviderJudge
from integrations.evaluation.metrics import (
    contains_match,
    exact_match,
    normalize_text,
    token_f1,
)
from integrations.providers.base import GenerationResult


class FakeJudge(DeepEvalBaseLLM):
    """DeepEval model that returns schema-shaped answers for the judge prompts."""

    def __init__(self):
        self.calls = 0
        super().__init__("fake-judge")

    def load_model(self):
        return self

    def get_model_name(self):
        return "fake:judge"

    def generate(self, prompt, schema=None, **kwargs):
        self.calls += 1
        payloads = {
            "Statements": {"statements": ["4"]},
            "Verdicts": {"verdicts": [{"verdict": "yes", "reason": "Supported."}]},
            "AnswerRelevancyScoreReason": {"reason": "The answer is relevant."},
            "Truths": {"truths": ["Two plus two equals four."]},
            "Claims": {"claims": ["4"]},
            "FaithfulnessScoreReason": {"reason": "No contradictions found."},
            "ContextualRelevancyVerdicts": {
                "verdicts": [
                    {"statement": "Two plus two equals four.", "verdict": "yes"}
                ]
            },
            "ContextualRelevancyScoreReason": {"reason": "Context is relevant."},
        }
        return schema.model_validate(payloads[schema.__name__])

    async def a_generate(self, prompt, schema=None, **kwargs):
        return self.generate(prompt, schema)


def test_normalisation_and_reference_metrics():
    assert normalize_text("  The  Capital, of France! ") == "capital of france"
    assert exact_match("Paris.", " paris ") == 1.0
    assert exact_match("Lyon", "Paris") == 0.0
    assert contains_match("The capital is Paris.", "paris") == 1.0
    assert contains_match("The capital is Lyon.", "paris") == 0.0
    assert token_f1("4", "4") == 1.0
    assert token_f1("not four", "4") == 0.0
    assert token_f1("the capital of france is paris", "paris") == pytest.approx(
        1 / 3, abs=1e-4
    )
    assert token_f1("", "paris") == 0.0


def test_registry_catalog_and_resolution():
    keys = [item["key"] for item in registry.catalog()]
    assert keys[:3] == ["exact_match", "contains_match", "token_f1"]
    assert "answer_relevancy" in keys
    assert "faithfulness" in keys
    assert "contextual_relevancy" in keys
    sources = {item["key"]: item["source"] for item in registry.catalog()}
    assert sources["answer_relevancy"] == "deepeval"
    assert sources["exact_match"] == "builtin"

    resolved = registry.resolve_metrics(["token_f1", "token_f1", "exact_match"])
    assert [definition.key for definition in resolved] == ["token_f1", "exact_match"]

    with pytest.raises(Exception):
        registry.resolve_metrics([])
    with pytest.raises(Exception):
        registry.resolve_metrics(["does_not_exist"])
    with pytest.raises(Exception):
        registry.resolve_metrics(["exact_match"] * 7)


def test_judge_metrics_are_hidden_when_unavailable(monkeypatch):
    monkeypatch.setattr(registry, "judge_metrics_available", lambda: False)
    assert [item["key"] for item in registry.catalog()] == [
        "exact_match",
        "contains_match",
        "token_f1",
    ]
    with pytest.raises(Exception):
        registry.resolve_metrics(["answer_relevancy"])


def test_judge_metrics_respect_platform_setting(settings):
    settings.EVALUATION_JUDGE_METRICS_ENABLED = False
    assert registry.judge_metrics_available() is False
    settings.EVALUATION_JUDGE_METRICS_ENABLED = True
    assert registry.judge_metrics_available() is True


def test_reference_metric_missing_expected_answer_is_a_metric_error():
    definition = registry.registry()["exact_match"]
    outcome = registry.evaluate(
        definition,
        case={"input": "q", "actual_output": "anything", "expected_output": ""},
        judge=None,
    )
    assert outcome["score"] is None
    assert "expected answer" in outcome["error"]


def test_reference_metric_scores_case():
    definition = registry.registry()["exact_match"]
    outcome = registry.evaluate(
        definition,
        case={"input": "2+2", "actual_output": "4", "expected_output": "4"},
        judge=None,
    )
    assert outcome["score"] == 1.0
    assert outcome["passed"] is True
    assert outcome["error"] is None


def test_context_metric_requires_context():
    definition = registry.registry()["faithfulness"]
    outcome = registry.evaluate(
        definition,
        case={"input": "q", "actual_output": "a", "expected_output": "", "context": []},
        judge=FakeJudge(),
    )
    assert outcome["score"] is None
    assert "retrieval context" in outcome["error"]


def test_deepeval_answer_relevancy_computes_a_score():
    definition = registry.registry()["answer_relevancy"]
    judge = FakeJudge()
    outcome = registry.evaluate(
        definition,
        case={
            "input": "What is 2+2?",
            "actual_output": "4",
            "expected_output": "4",
            "context": [],
        },
        judge=judge,
    )
    assert outcome["error"] is None
    assert isinstance(outcome["score"], float)
    assert 0.0 <= outcome["score"] <= 1.0
    assert judge.calls > 0


def test_deepeval_faithfulness_and_contextual_relevancy_compute_scores():
    case = {
        "input": "What is 2+2?",
        "actual_output": "4",
        "expected_output": "4",
        "context": ["Two plus two equals four."],
    }
    for key in ("faithfulness", "contextual_relevancy"):
        outcome = registry.evaluate(
            registry.registry()[key], case=case, judge=FakeJudge()
        )
        assert outcome["error"] is None, key
        assert isinstance(outcome["score"], float), key
        assert outcome["threshold"] == 0.5


class SampleSchema(BaseModel):
    answer: str


class StubAdapter:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return GenerationResult(
            provider="ollama",
            model_id=request.model_id,
            content=self.content,
            error=self.error,
        )


def test_provider_judge_parses_fenced_json_into_the_requested_schema():
    adapter = StubAdapter(content='```json\n{"answer": "4"}\n```')
    judge = ProviderJudge(adapter, "llama3.2")
    parsed = judge.generate("Score this", schema=SampleSchema)
    assert parsed.answer == "4"
    assert judge.calls == 1
    assert adapter.requests[0].model_id == "llama3.2"


def test_provider_judge_raises_clean_errors():
    empty = ProviderJudge(StubAdapter(content=None), "llama3.2")
    with pytest.raises(JudgeError):
        empty.generate("Score this", schema=SampleSchema)

    broken = ProviderJudge(
        StubAdapter(error={"category": "provider_error", "message": "boom"}),
        "llama3.2",
    )
    with pytest.raises(JudgeError):
        broken.generate("Score this", schema=SampleSchema)

    bad_json = ProviderJudge(StubAdapter(content="no json here"), "llama3.2")
    with pytest.raises(JudgeError):
        bad_json.generate("Score this", schema=SampleSchema)
