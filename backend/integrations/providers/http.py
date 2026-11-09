"""Small JSON transport for provider adapters; never includes credentials in errors."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 0.25
DEFAULT_MAX_CONCURRENCY = 8


class ProviderRequestError(RuntimeError):
    def __init__(self, category: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


_slots: threading.BoundedSemaphore | None = None
_slots_size = 0
_slots_lock = threading.Lock()


def _concurrency_slots() -> threading.BoundedSemaphore:
    """Return the process-wide provider call limiter.

    Celery runs multiple processes, so this limits concurrent in-flight calls
    per worker process rather than globally across the deployment.
    """
    global _slots, _slots_size
    size = max(1, int(getattr(settings, "PROVIDER_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)))
    with _slots_lock:
        if _slots is None or _slots_size != size:
            _slots = threading.BoundedSemaphore(size)
            _slots_size = size
        return _slots


def _retry_delay(attempt: int) -> float:
    base = float(
        getattr(settings, "PROVIDER_RETRY_BACKOFF_SECONDS", DEFAULT_BACKOFF_SECONDS)
    )
    return max(0.0, base) * (2**attempt)


def request_json(
    *,
    url: str,
    method: str = "GET",
    payload=None,
    api_key: str | None = None,
    timeout: float | None = None,
):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    effective_timeout = float(
        timeout
        if timeout is not None
        else getattr(settings, "PROVIDER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    )
    max_retries = max(
        0, int(getattr(settings, "PROVIDER_MAX_RETRIES", DEFAULT_MAX_RETRIES))
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    slots = _concurrency_slots()
    acquire_timeout = float(
        getattr(settings, "PROVIDER_CONCURRENCY_WAIT_SECONDS", 5.0)
    )

    last_error: ProviderRequestError | None = None
    for attempt in range(max_retries + 1):
        if not slots.acquire(timeout=max(0.0, acquire_timeout)):
            raise ProviderRequestError(
                "busy", "The provider is handling too many concurrent requests."
            )
        request = urllib.request.Request(
            url, data=body, headers=headers, method=method
        )
        try:
            try:
                with opener.open(request, timeout=effective_timeout) as response:
                    raw = response.read(2_000_001)
            except urllib.error.HTTPError as exc:
                code = exc.code
                if code in (401, 403):
                    category, message = (
                        "authentication_failed",
                        "Provider rejected the configured credentials.",
                    )
                elif code == 404:
                    category, message = (
                        "not_found",
                        "Provider endpoint or model was not found.",
                    )
                elif code == 429:
                    category, message = (
                        "rate_limited",
                        "Provider rate limit reached.",
                    )
                elif code in (400, 422):
                    category, message = (
                        "invalid_request",
                        "Provider rejected the request. Check the selected model and settings.",
                    )
                elif 300 <= code < 400:
                    category, message = (
                        "redirect_blocked",
                        "Provider redirects are not allowed.",
                    )
                else:
                    category, message = (
                        "provider_error",
                        f"Provider returned HTTP {code}.",
                    )
                last_error = ProviderRequestError(category, message, code)
                if code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise last_error from None
            except (urllib.error.URLError, TimeoutError, OSError):
                last_error = ProviderRequestError(
                    "network_error", "Could not reach the provider endpoint."
                )
                if attempt < max_retries:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise last_error from None
        finally:
            slots.release()

        if len(raw) > 2_000_000:
            raise ProviderRequestError(
                "invalid_response", "Provider response exceeded the allowed size."
            )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderRequestError(
                "invalid_response", "Provider returned an invalid JSON response."
            ) from None
        if not isinstance(value, dict):
            raise ProviderRequestError(
                "invalid_response", "Provider returned an unexpected response."
            )
        return value

    # The loop either returns or raises; keep a defensive fallback for typing.
    raise last_error or ProviderRequestError(
        "network_error", "Could not reach the provider endpoint."
    )
