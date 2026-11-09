import json
import threading
import urllib.error

import pytest

from integrations.providers import http as provider_http
from integrations.providers.http import ProviderRequestError, request_json


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, limit: int) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Opener:
    def __init__(self, effects):
        self.effects = list(effects)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append({"request": request, "timeout": timeout})
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def _patch_opener(monkeypatch, opener):
    monkeypatch.setattr(
        "urllib.request.build_opener", lambda *handlers: opener
    )


def test_provider_retries_transient_network_failure_then_recovers(monkeypatch, settings):
    settings.PROVIDER_MAX_RETRIES = 2
    settings.PROVIDER_RETRY_BACKOFF_SECONDS = 0
    opener = _Opener(
        [
            urllib.error.URLError("temporary"),
            _Response({"ok": True}),
        ]
    )
    _patch_opener(monkeypatch, opener)
    sleeps: list[float] = []
    monkeypatch.setattr(provider_http.time, "sleep", sleeps.append)

    assert request_json(url="https://provider.example/v1/models") == {"ok": True}
    assert len(opener.calls) == 2
    assert sleeps == [0.0]


def test_provider_retries_retryable_http_status_then_recovers(monkeypatch, settings):
    settings.PROVIDER_MAX_RETRIES = 1
    settings.PROVIDER_RETRY_BACKOFF_SECONDS = 0
    opener = _Opener(
        [
            urllib.error.HTTPError(
                "https://provider.example/v1/models", 503, "Unavailable", {}, None
            ),
            _Response({"ok": True}),
        ]
    )
    _patch_opener(monkeypatch, opener)

    assert request_json(url="https://provider.example/v1/models") == {"ok": True}
    assert len(opener.calls) == 2


def test_provider_gives_up_after_configured_retries(monkeypatch, settings):
    settings.PROVIDER_MAX_RETRIES = 2
    settings.PROVIDER_RETRY_BACKOFF_SECONDS = 0
    opener = _Opener(
        [
            urllib.error.URLError("down"),
            urllib.error.URLError("down"),
            urllib.error.URLError("down"),
        ]
    )
    _patch_opener(monkeypatch, opener)

    with pytest.raises(ProviderRequestError) as excinfo:
        request_json(url="https://provider.example/v1/models")
    assert excinfo.value.category == "network_error"
    assert len(opener.calls) == 3


def test_provider_does_not_retry_authentication_failures(monkeypatch, settings):
    settings.PROVIDER_MAX_RETRIES = 3
    opener = _Opener(
        [
            urllib.error.HTTPError(
                "https://provider.example/v1/models", 401, "Unauthorized", {}, None
            )
        ]
    )
    _patch_opener(monkeypatch, opener)

    with pytest.raises(ProviderRequestError) as excinfo:
        request_json(url="https://provider.example/v1/models", api_key="bad-key")
    assert excinfo.value.category == "authentication_failed"
    assert len(opener.calls) == 1


def test_provider_timeout_is_configurable_and_passed_to_transport(monkeypatch, settings):
    settings.PROVIDER_TIMEOUT_SECONDS = 7.5
    opener = _Opener([_Response({"ok": True})])
    _patch_opener(monkeypatch, opener)

    request_json(url="https://provider.example/v1/models")
    assert opener.calls[0]["timeout"] == 7.5


def test_provider_concurrency_limit_reports_busy(monkeypatch, settings):
    settings.PROVIDER_CONCURRENCY_WAIT_SECONDS = 0.01
    saturated = threading.BoundedSemaphore(1)
    saturated.acquire()
    monkeypatch.setattr(provider_http, "_concurrency_slots", lambda: saturated)

    with pytest.raises(ProviderRequestError) as excinfo:
        request_json(url="https://provider.example/v1/models")
    assert excinfo.value.category == "busy"
