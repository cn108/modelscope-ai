"""Cloud Z.ai and local Ollama adapters."""

import ipaddress
import time
from urllib.parse import urlsplit

from integrations.providers.base import (
    ConnectionStatus,
    GenerationRequest,
    GenerationResult,
    ModelInfo,
    ProviderAdapter,
    ProviderCapabilities,
)
from integrations.providers.http import ProviderRequestError, request_json

ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
ZAI_MODELS = (
    ModelInfo("zai", "glm-5.3", "GLM-5.3"),
    ModelInfo("zai", "glm-5.3-flash", "GLM-5.3 Flash"),
)


def validate_lmstudio_endpoint(endpoint: str) -> str:
    """Allow only a local LM Studio OpenAI-compatible endpoint.

    LM Studio defaults to port 1234 and serves the OpenAI API under ``/v1``.
    Cloud/external hosts are rejected for the same SSRF reason as Ollama.
    """
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("LM Studio endpoint must be an absolute HTTP(S) URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("LM Studio endpoint cannot include credentials, query, or fragment.")
    host = parts.hostname.lower().rstrip(".")
    if host not in {"localhost", "host.docker.internal"}:
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError(
                "LM Studio endpoint host must be localhost, host.docker.internal, or a loopback IP address."
            ) from exc
        if not address.is_loopback:
            raise ValueError(
                "LM Studio endpoint must use localhost, host.docker.internal, or a loopback IP address."
            )
    if parts.port not in (None, 1234):
        raise ValueError("LM Studio endpoint must use the standard local port 1234.")
    path = parts.path.rstrip("/")
    if path not in {"", "/v1"}:
        raise ValueError("LM Studio endpoint base path must be /v1 or the root.")
    return f"{parts.scheme}://{parts.netloc}/v1"


def validate_ollama_endpoint(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Ollama endpoint must be an absolute HTTP(S) URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Ollama endpoint cannot include credentials, query, or fragment.")
    host = parts.hostname.lower().rstrip(".")
    if host not in {"localhost", "host.docker.internal"}:
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("Ollama endpoint host must be localhost, host.docker.internal, or a loopback IP address.") from exc
        if not address.is_loopback:
            raise ValueError("Ollama endpoint must use localhost, host.docker.internal, or a loopback IP address.")
    if parts.port not in (None, 11434):
        raise ValueError("Ollama endpoint must use the standard local port 11434.")
    path = parts.path.rstrip("/")
    if path not in {"", "/api"}:
        raise ValueError("Ollama endpoint base path must be /api or the root.")
    return f"{parts.scheme}://{parts.netloc}"


class ZaiAdapter(ProviderAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_model_listing=True)

    def list_models(self) -> list[ModelInfo]:
        # Z.ai's standard API does not document a model-list endpoint. Keep the
        # account-verified model catalogue explicit instead of guessing support.
        return list(ZAI_MODELS)

    def validate_connection(self) -> ConnectionStatus:
        try:
            request_json(
                url=f"{ZAI_BASE_URL}/chat/completions",
                method="POST",
                api_key=self.api_key,
                payload={
                    "model": ZAI_MODELS[0].model_id,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 2,
                },
            )
        except ProviderRequestError as exc:
            return ConnectionStatus(False, str(exc))
        return ConnectionStatus(True, "Z.ai API key and chat endpoint are valid.")

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.monotonic()
        try:
            response = request_json(
                url=f"{ZAI_BASE_URL}/chat/completions",
                method="POST",
                api_key=self.api_key,
                payload={
                    "model": request.model_id,
                    "messages": request.messages,
                    **request.parameters,
                },
            )
            choice = response["choices"][0]
            usage = response.get("usage") or {}
            return GenerationResult(
                provider="zai",
                model_id=request.model_id,
                content=(choice.get("message") or {}).get("content"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                tokens_are_provider_reported=bool(usage),
                latency_ms=(time.monotonic() - started) * 1000,
                finish_reason=choice.get("finish_reason"),
                request_id=response.get("request_id") or response.get("id"),
            )
        except (ProviderRequestError, KeyError, IndexError, TypeError) as exc:
            if isinstance(exc, ProviderRequestError):
                category, message = exc.category, str(exc)
            else:
                category, message = "invalid_response", "Z.ai returned an unexpected response."
            return GenerationResult(
                provider="zai",
                model_id=request.model_id,
                content=None,
                latency_ms=(time.monotonic() - started) * 1000,
                error={"category": category, "message": message},
            )


class LmStudioAdapter(ProviderAdapter):
    """Local LM Studio's OpenAI-compatible chat completions API."""

    def __init__(self, endpoint: str, api_key: str | None = None):
        self.base_url = validate_lmstudio_endpoint(endpoint)
        self.api_key = api_key

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_model_listing=True)

    def list_models(self) -> list[ModelInfo]:
        response = request_json(
            url=f"{self.base_url}/models", api_key=self.api_key
        )
        data = response.get("data", [])
        if not isinstance(data, list):
            raise ProviderRequestError(
                "invalid_response", "LM Studio returned an unexpected model list."
            )
        return [
            ModelInfo("lmstudio", item["id"], item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    def validate_connection(self) -> ConnectionStatus:
        try:
            self.list_models()
        except ProviderRequestError as exc:
            return ConnectionStatus(False, str(exc))
        return ConnectionStatus(True, "Local LM Studio endpoint is reachable.")

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.monotonic()
        try:
            response = request_json(
                url=f"{self.base_url}/chat/completions",
                method="POST",
                api_key=self.api_key,
                payload={
                    "model": request.model_id,
                    "messages": request.messages,
                    **request.parameters,
                },
            )
            choice = response["choices"][0]
            usage = response.get("usage") or {}
            return GenerationResult(
                provider="lmstudio",
                model_id=request.model_id,
                content=(choice.get("message") or {}).get("content"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                tokens_are_provider_reported=bool(usage),
                latency_ms=(time.monotonic() - started) * 1000,
                finish_reason=choice.get("finish_reason"),
                request_id=response.get("id"),
            )
        except (ProviderRequestError, KeyError, IndexError, TypeError) as exc:
            if isinstance(exc, ProviderRequestError):
                category, message = exc.category, str(exc)
            else:
                category, message = (
                    "invalid_response",
                    "LM Studio returned an unexpected response.",
                )
            return GenerationResult(
                provider="lmstudio",
                model_id=request.model_id,
                content=None,
                latency_ms=(time.monotonic() - started) * 1000,
                error={"category": category, "message": message},
            )


class OllamaAdapter(ProviderAdapter):
    def __init__(self, endpoint: str):
        self.base_url = validate_ollama_endpoint(endpoint)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_model_listing=True)

    def list_models(self) -> list[ModelInfo]:
        response = request_json(url=f"{self.base_url}/api/tags")
        models = response.get("models", [])
        if not isinstance(models, list):
            raise ProviderRequestError("invalid_response", "Ollama returned an unexpected model list.")
        return [
            ModelInfo("ollama", item["name"], item.get("details", {}).get("family"))
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def validate_connection(self) -> ConnectionStatus:
        try:
            self.list_models()
        except ProviderRequestError as exc:
            return ConnectionStatus(False, str(exc))
        return ConnectionStatus(True, "Local Ollama endpoint is reachable.")

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.monotonic()
        try:
            response = request_json(
                url=f"{self.base_url}/api/chat",
                method="POST",
                payload={
                    "model": request.model_id,
                    "messages": request.messages,
                    "stream": False,
                    "options": request.parameters,
                },
            )
            message = response.get("message") or {}
            input_tokens = response.get("prompt_eval_count")
            output_tokens = response.get("eval_count")
            return GenerationResult(
                provider="ollama",
                model_id=request.model_id,
                content=message.get("content"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tokens_are_provider_reported=input_tokens is not None or output_tokens is not None,
                latency_ms=(time.monotonic() - started) * 1000,
                finish_reason=response.get("done_reason"),
            )
        except (ProviderRequestError, KeyError, TypeError) as exc:
            if isinstance(exc, ProviderRequestError):
                category, message = exc.category, str(exc)
            else:
                category, message = "invalid_response", "Ollama returned an unexpected response."
            return GenerationResult(
                provider="ollama",
                model_id=request.model_id,
                content=None,
                latency_ms=(time.monotonic() - started) * 1000,
                error={"category": category, "message": message},
            )
