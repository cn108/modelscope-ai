"""Provider adapter interface (specification section 4).

Business services must call this internal interface, never vendor SDKs
directly. Concrete adapters (OpenAI-compatible, Hugging Face, LM Studio,
Ollama) arrive in Milestone 3; this module fixes the contract now so callers
and tests can target it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_model_listing: bool = False
    supports_streaming: bool = False
    supports_structured_output: bool = False


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model_id: str
    display_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectionStatus:
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class GenerationRequest:
    model_id: str
    messages: list[dict[str, str]]
    parameters: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    """Normalised result per section 4. Unavailable measurements stay None —
    never fabricate token counts, costs or latencies."""

    provider: str
    model_id: str
    content: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_are_provider_reported: bool = False
    latency_ms: float | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    error: dict[str, Any] | None = None


class ProviderAdapter(ABC):
    """Common internal interface every provider adapter implements."""

    @abstractmethod
    def validate_connection(self) -> ConnectionStatus: ...

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    def list_models(self) -> list[ModelInfo]:
        if not self.capabilities().supports_model_listing:
            raise NotImplementedError("Provider does not support model listing.")
        raise NotImplementedError  # concrete adapters override

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
