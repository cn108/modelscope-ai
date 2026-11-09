"""Small JSON transport for provider adapters; never includes credentials in errors."""

import json
import urllib.error
import urllib.request


class ProviderRequestError(RuntimeError):
    def __init__(self, category: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def request_json(*, url: str, method: str = "GET", payload=None, api_key: str | None = None):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(2_000_001)
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code in (401, 403):
            category, message = "authentication_failed", "Provider rejected the configured credentials."
        elif code == 404:
            category, message = "not_found", "Provider endpoint or model was not found."
        elif code == 429:
            category, message = "rate_limited", "Provider rate limit reached."
        elif code in (400, 422):
            category, message = "invalid_request", "Provider rejected the request. Check the selected model and settings."
        elif 300 <= code < 400:
            category, message = "redirect_blocked", "Provider redirects are not allowed."
        else:
            category, message = "provider_error", f"Provider returned HTTP {code}."
        raise ProviderRequestError(category, message, code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderRequestError("network_error", "Could not reach the provider endpoint.") from None

    if len(raw) > 2_000_000:
        raise ProviderRequestError("invalid_response", "Provider response exceeded the allowed size.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderRequestError("invalid_response", "Provider returned an invalid JSON response.") from None
    if not isinstance(value, dict):
        raise ProviderRequestError("invalid_response", "Provider returned an unexpected response.")
    return value
