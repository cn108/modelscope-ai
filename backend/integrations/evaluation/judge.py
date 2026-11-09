"""DeepEval judge backed by a configured ModelScope provider.

DeepEval normally calls OpenAI. Here it calls the same M3 adapter that powers
the playground, so evaluation never introduces a second provider path.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_ERROR_REPORTING", "NO")

from deepeval.models import DeepEvalBaseLLM  # noqa: E402  (env flags must precede import)

from integrations.providers.base import GenerationRequest  # noqa: E402

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class JudgeError(RuntimeError):
    """Raised when the judge model cannot produce a usable answer."""


def extract_json(text: str) -> str:
    """Pull the first JSON object out of a model answer."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    candidate = candidate.strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JudgeError("The judge model did not return JSON.")
    return candidate[start : end + 1]


class ProviderJudge(DeepEvalBaseLLM):
    """A DeepEval model that proxies through a provider adapter."""

    def __init__(self, adapter, model_id: str, parameters: dict[str, Any] | None = None):
        self.adapter = adapter
        self.model_id = model_id
        self.parameters = parameters or {}
        self.calls = 0
        super().__init__(model_id)

    def load_model(self):  # DeepEvalBaseLLM expects this to return the model
        return self

    def get_model_name(self) -> str:
        return f"modelscope:{self.model_id}"

    def generate(self, prompt: str, schema=None, **kwargs):
        self.calls += 1
        result = self.adapter.generate(
            GenerationRequest(
                model_id=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                parameters=self.parameters,
            )
        )
        if result.error or not result.content:
            message = (result.error or {}).get("message") or "The judge model returned no content."
            raise JudgeError(str(message)[:300])
        text = result.content
        if schema is None:
            return text
        try:
            return schema.model_validate_json(extract_json(text))
        except JudgeError:
            raise
        except Exception as exc:  # noqa: BLE001 - pydantic/JSON errors become judge errors
            raise JudgeError(
                "The judge model returned data that did not match the metric schema."
            ) from exc

    async def a_generate(self, prompt: str, schema=None, **kwargs):
        return self.generate(prompt, schema)

    def batch_generate(self, prompts: list[str], **kwargs):
        return [self.generate(prompt) for prompt in prompts]


def build_judge(provider, model_id: str, parameters: dict[str, Any] | None = None) -> ProviderJudge:
    """Create a judge from a provider config using the M3 adapter factory."""
    from apps.providers.services import adapter_for

    return ProviderJudge(adapter_for(provider), model_id, parameters)


def dumps(value: Any) -> str:
    """Small helper kept for callers that need deterministic JSON text."""
    return json.dumps(value, sort_keys=True, default=str)
