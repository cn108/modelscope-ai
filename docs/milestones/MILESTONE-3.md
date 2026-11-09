# Milestone 3 — Provider layer

Date: 2026-11-09 · Status: **complete for Z.ai, Ollama and LM Studio; live Z.ai still
requires an operator key**

## Delivered

- Provider adapters behind one interface: Z.ai (OpenAI-compatible cloud API), Ollama
  (local HTTP API) and LM Studio (local OpenAI-compatible API on port 1234).
- Fernet-encrypted API keys with rotation support; secrets are never returned by the API.
- Connection testing, model discovery, provider CRUD, project scoping, RBAC and audit
  events.
- Endpoint allow-lists that reject non-local Ollama/LM Studio hosts and block redirects,
  credentials in URLs, queries and fragments (SSRF hardening).
- Configurable timeout, bounded retries with exponential backoff for transient failures,
  and a per-worker-process concurrency limit.
- Redacted provider errors; failures are returned to the caller rather than leaking keys
  or raw responses.

## Verification

| Check | Evidence |
|---|---|
| Ollama live | `llama3.2:1b` discovered and executed through the Docker stack |
| LM Studio | endpoint validation and OpenAI-compatible adapter covered by automated tests |
| Z.ai adapter | request/response normalisation, error redaction and model catalogue tested against a stub |
| Retry/timeout/concurrency | deterministic transport tests cover recovery, exhausted retries, non-retryable auth failures, configured timeout and busy rejection |
| Secret isolation | API responses and audit payloads never contain the API key; encrypted storage checked in tests |
| Tenant isolation | foreign-project provider reads return 404; member mutation returns 403 |

## Limitations

- **No live Z.ai call** was possible without an operator-supplied API key. The adapter is
  implemented and tested against a deterministic transport stub.
- LM Studio was not available on the acceptance machine, so its live verification is
  limited to adapter and endpoint tests.
- Retry/concurrency limits are per worker process; horizontal scaling requires
  accounting for the number of worker replicas.
