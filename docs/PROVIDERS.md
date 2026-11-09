# Provider setup

Providers are configured **per project**. A provider config contains the adapter kind,
endpoint, non-secret defaults and an optional encrypted secret. The browser never
receives the secret; only `has_secret: true/false` is returned.

## Supported providers

| Kind | Adapter | Authentication | Status |
|---|---|---|---|
| `zai` | Z.ai OpenAI-compatible chat API | API key | Implemented; live Z.ai verification still requires an operator key. |
| `ollama` | Local Ollama HTTP API | None | Implemented and live-tested with Ollama `0.40.13` / `llama3.2:1b`. |
| `lmstudio` | Local LM Studio OpenAI-compatible API | Optional bearer key | Implemented; adapter/endpoint tests pass, no live LM Studio instance was available. |
| Generic OpenAI-compatible | — | — | **Not implemented.** Only the Z.ai adapter is preconfigured for cloud use. |
| Hugging Face | — | — | **Not implemented.** No adapter or integration exists. |

The specification also names Hugging Face and generic OpenAI-compatible APIs; those are
recorded as scope gaps in [ADR-0005](adr/ADR-0005-provider-scope.md) and
[HANDOVER.md](HANDOVER.md).

## Transient failures, timeouts and concurrency

All adapters use the shared transport (`integrations/providers/http.py`):

- requests are bounded by `PROVIDER_TIMEOUT_SECONDS` (default 60);
- network errors, HTTP 429 and HTTP 5xx are retried up to `PROVIDER_MAX_RETRIES`
  (default 2) with exponential backoff (`PROVIDER_RETRY_BACKOFF_SECONDS`, default 0.25);
- 401/403/404/400/422 and blocked redirects are never retried;
- each worker process limits in-flight calls with `PROVIDER_MAX_CONCURRENCY` (default 8);
- exhausted retries surface as a structured result error, not a lost run.

The limits are per process. Raising worker concurrency or adding worker replicas also
raises the maximum number of concurrent provider calls.

## LM Studio

LM Studio serves an OpenAI-compatible API on local port 1234 by default. Start its local
server, load a model, then create a provider with kind `lmstudio`:

```text
http://localhost:1234/v1
http://host.docker.internal:1234/v1
```

Endpoint rules: HTTP(S), `localhost`/`host.docker.internal`/loopback IP only, no embedded
credentials/query/fragment, port 1234 or omitted, path empty or `/v1`. The adapter uses
`/models` for discovery and `/chat/completions` for generation. An optional API key is
supported and encrypted like other provider secrets; it is never returned.

The Compose stack already maps `host.docker.internal`, so a host LM Studio server is
reachable as `http://host.docker.internal:1234/v1`. Live LM Studio verification was not
possible on the acceptance machine; the adapter, URL rules and failure paths are covered
by automated tests.

## Z.ai

### Prerequisites

- A Z.ai account and API key with access to the chat-completions endpoint.
- Outbound HTTPS access from the API/worker to `https://api.z.ai/api/paas/v4`.
- `PROVIDER_SECRET_KEYS` configured in the backend environment so the key can be
  encrypted at rest.

### Create the provider

In the project's **Providers** screen, choose **Z.ai**, enter a name and API key. The
endpoint is fixed to `https://api.z.ai/api/paas/v4` and cannot be overridden.

Equivalent API request:

```bash
curl -sS -X POST "http://localhost:8000/api/v1/projects/$PROJECT_ID/providers/" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Z.ai production",
    "kind": "zai",
    "endpoint": "https://api.z.ai/api/paas/v4",
    "api_key": "<z.ai api key>",
    "settings": {"temperature": 0.2}
  }'
```

The response contains `has_secret: true` but never the key.

### Models

Z.ai's standard API does not document a model-list endpoint, so the adapter exposes an
explicit, account-verified catalogue:

- `glm-5.3` (`GLM-5.3`)
- `glm-5.3-flash` (`GLM-5.3 Flash`)

Refresh models with `GET /providers/{id}/models/`. This writes/updates `ModelConfig`
rows for the provider. It does not invent models outside the explicit catalogue.

### Connection test

`POST /providers/{id}/test/` sends a minimal chat-completions request. A success response
looks like:

```json
{"ok": true, "status": "connected", "detail": "Z.ai API key and chat endpoint are valid."}
```

A failure is recorded as `connection_status: "error"` with a sanitized detail. Never put
keys in logs or screenshots.

### Current verification

The adapter and connection flow are covered by automated tests. A **live** Z.ai call has
not been verified in this repository because no operator API key was supplied. Treat
production Z.ai behavior as unverified until you run the provider test and a small
playground call with a real key.

## Ollama

### Prerequisites

- Ollama installed on the host or a reachable local machine.
- A pulled model, for example:

```bash
ollama pull llama3.2
```

- The Ollama server running:

```bash
ollama serve
```

By default Ollama listens on `127.0.0.1:11434`. If the backend/worker runs in Docker, the
container reaches the host through `host.docker.internal` (the Compose file adds the
Linux host-gateway mapping). On Linux, make sure Ollama listens on an interface reachable
from Docker, for example:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

Only do this on a trusted network; Ollama does not provide authentication.

### Endpoint rules

The local endpoint validator accepts:

- scheme `http` or `https`;
- host `localhost`, `host.docker.internal`, or a loopback IP address such as
  `127.0.0.1` / `::1`;
- no username, password, query string or fragment;
- port omitted or exactly `11434`;
- path empty or exactly `/api`.

Examples that are accepted:

```text
http://localhost:11434
http://localhost:11434/api
http://127.0.0.1:11434
http://host.docker.internal:11434
```

These are rejected:

```text
http://192.168.1.20:11434          # non-loopback IP
http://localhost:1234/v1           # rejected by Ollama; use the LM Studio kind
https://user:pass@localhost:11434  # embedded credentials
http://localhost:11434/api?x=1     # query string
```

The validator normalises the stored endpoint to `scheme://host:port`.

### Create the provider

```bash
curl -sS -X POST "http://localhost:8000/api/v1/projects/$PROJECT_ID/providers/" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Local Ollama",
    "kind": "ollama",
    "endpoint": "http://localhost:11434",
    "settings": {"temperature": 0.1}
  }'
```

Ollama does not use an API key. Sending `api_key` for an Ollama provider is rejected.

### Refresh and test

```bash
# Fetch /api/tags and persist model rows.
curl -sS "http://localhost:8000/api/v1/providers/$PROVIDER_ID/models/" \
  -H "Authorization: Bearer $TOKEN"

# Test connectivity.
curl -sS -X POST "http://localhost:8000/api/v1/providers/$PROVIDER_ID/test/" \
  -H "Authorization: Bearer $TOKEN"
```

A successful local test returns:

```json
{"ok": true, "status": "connected", "detail": "Local Ollama endpoint is reachable."}
```

### Docker networking

| Where the backend runs | Endpoint to use |
|---|---|
| Native on the host | `http://localhost:11434` |
| In the supplied Compose stack, Ollama on the host | `http://host.docker.internal:11434` |
| Ollama in another container on the same network | `http://<service-name>:11434` is **not** accepted by the validator unless the host resolves to a loopback/host-gateway name. Use host networking or expose Ollama on the host. |

If the connection fails, check that the Ollama process is listening, that the host
firewall allows the port, and that the container can resolve `host.docker.internal`.

### Live evidence

The AI security testing acceptance run used Ollama `0.40.13` with `llama3.2:1b` and
recorded 18 actual responses with 0 provider errors. That verifies the Ollama adapter,
not Z.ai or every Ollama model. See [MILESTONE-9.md](milestones/MILESTONE-9.md).

## Provider settings

`settings` is a JSON object of non-secret inference defaults. Supported keys:

`temperature`, `top_p`, `max_tokens`, `stop`, `seed`, `presence_penalty`,
`frequency_penalty`.

At execution time, provider defaults are merged with execution-level parameters; the
execution-level value wins. Unknown keys, oversized settings and non-object values are
rejected.

## Secret storage and rotation

Provider API keys are encrypted with Fernet. The first key in `PROVIDER_SECRET_KEYS`
encrypts new secrets; every key in the list can decrypt. Keys live only in the
environment, never in PostgreSQL plaintext, logs or API responses.

To rotate:

1. Generate a new Fernet key.
2. Prepend it to `PROVIDER_SECRET_KEYS` and restart the API/worker.
3. Re-enter/update each provider's API key so it is re-encrypted with the new first key.
   There is no automatic bulk re-encryption command.
4. Verify each provider connection.
5. Remove the old key only after every stored secret has been re-encrypted; otherwise old
   secrets become undecryptable.

If `PROVIDER_SECRET_KEYS` is empty or invalid, creating/updating/testing a provider that
needs a secret fails with a configuration error. Do not delete the old key before the
database and all secrets have been migrated.

## Troubleshooting provider setup

| Symptom | Likely cause | Action |
|---|---|---|
| `PROVIDER_SECRET_KEYS is not configured` | Missing encryption key | Generate a Fernet key and set `PROVIDER_SECRET_KEYS` in `.env`, then restart backend/worker. |
| `Secret could not be decrypted with any configured key` | Key changed/removed, or restored database without the old key | Restore the matching key or re-enter the provider API key. Do not discard the old key until migration is complete. |
| Ollama endpoint rejected | Non-loopback host, non-11434 port, `/v1` path, query/credentials in URL | Use `http://localhost:11434` or `http://host.docker.internal:11434`; see the rules above. |
| Ollama connection fails from Compose | Ollama bound only to host loopback or firewall blocked | Start Ollama on `0.0.0.0:11434` on a trusted network and check `host.docker.internal` resolution. |
| Z.ai test fails | Invalid/expired key, outbound network block, provider outage | Verify the key outside the app, check egress, then retry. Details are sanitized in the API. |
| Model list empty | Provider has no models or Ollama has none pulled | Run `ollama pull <model>` or check the Z.ai account catalogue. |
| AI security test rejects the model | Model is not a `ModelConfig` row for that provider | Refresh the provider's model list first; AI security testing requires a discovered/configured model, while playground/evaluation model IDs are free-form. |

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for application-wide issues.
