# API guide

The API is a versioned JSON REST API at `/api/v1/`. The generated OpenAPI schema is the
authoritative field-level reference:

- Swagger UI: `http://localhost:8000/api/docs/`
- OpenAPI schema: `http://localhost:8000/api/schema/`

This guide covers authentication, conventions, the endpoint map and representative
requests/responses. If this guide and the generated schema disagree, the schema and code
win.

## Conventions

- **Base path:** `/api/v1/`
- **Content type:** `application/json` except dataset file imports, which use
  `multipart/form-data`.
- **IDs:** UUID strings.
- **Timestamps:** ISO 8601 UTC.
- **Authentication:** `Authorization: Bearer <access token>`.
- **Pagination:** list responses use `count`, `next`, `previous` and `results`.
  `page_size` may be set up to 200; the default is 50.
- **Cross-tenant reads:** return `404` rather than revealing that a resource exists.
- **Errors:** a stable envelope:

```json
{
  "error": {
    "code": "invalid",
    "message": "Invalid input.",
    "details": {
      "name": ["This field is required."]
    }
  }
}
```

Common status codes are `200`, `201`, `204`, `400`, `401`, `403`, `404`, `409` and `503`.
A broker/queue failure can be stored as a failed job and is visible in the job's status.

## Authentication

### Register

```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "owner@example.com",
    "password": "Str0ng-Passw0rd!",
    "display_name": "Workspace Owner"
  }'
```

```json
{
  "user": {
    "id": "2f4f4f3a-6f6f-4f4f-8f4f-4f4f4f4f4f4f",
    "email": "owner@example.com",
    "display_name": "Workspace Owner",
    "created_at": "2026-11-09T12:00:00Z"
  },
  "tokens": {
    "access": "<access token>",
    "refresh": "<refresh token>"
  }
}
```

Registration returns `201` and signs the account in immediately. Email addresses are
normalised to lower case. A duplicate email returns `409` with code `email_taken`.

### Login

```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"Str0ng-Passw0rd!"}'
```

Bad credentials return `401` with the same generic message for unknown emails and wrong
passwords.

### Refresh

```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/refresh/ \
  -H 'Content-Type: application/json' \
  -d '{"refresh":"<refresh token>"}'
```

Refresh tokens rotate. The old token is blacklisted after rotation and cannot be reused.
Access tokens last 15 minutes by default; refresh tokens last 7 days.

### Current user

```bash
curl -sS http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer $TOKEN"
```

## Endpoint map

### Identity and tenancy

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register/` | Create account and return JWT pair. |
| POST | `/auth/login/` | Exchange email/password for JWT pair. |
| POST | `/auth/refresh/` | Rotate refresh token and return a new pair. |
| GET | `/auth/me/` | Current user profile. |
| GET/POST | `/workspaces/` | List or create workspaces. |
| GET/PATCH/DELETE | `/workspaces/{id}/` | Read, rename/configure or delete a workspace. |
| GET/POST | `/workspaces/{id}/members/` | List or add members. |
| PATCH/DELETE | `/workspaces/{id}/members/{membership_id}/` | Change a member role or remove a member. |
| GET/POST | `/projects/` | List projects (optional `?workspace=`) or create one. |
| GET/PATCH/DELETE | `/projects/{id}/` | Read, update or delete a project. |

### Providers, prompts and playground

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/projects/{id}/providers/` | List or create project providers. |
| GET/PATCH/DELETE | `/providers/{id}/` | Read, update or delete a provider. |
| POST | `/providers/{id}/test/` | Test provider connectivity. |
| GET | `/providers/{id}/models/` | Refresh and list available models. |
| GET/POST | `/projects/{id}/prompts/` | List or create saved prompts. |
| GET/PATCH/DELETE | `/prompts/{id}/` | Read, update or delete a prompt. |
| GET | `/prompts/{id}/versions/` | List append-only prompt versions. |
| POST | `/prompts/{id}/versions/restore/` | Restore a version by creating a new version. |
| POST | `/prompts/{id}/duplicate/` | Duplicate a prompt. |
| GET/POST | `/projects/{id}/executions/` | List or run playground executions. |
| GET | `/executions/{id}/` | Read an execution and its per-model results. |
| POST | `/executions/{id}/rerun/` | Create a new execution from the stored snapshot. |

### Datasets and evaluations

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/projects/{id}/datasets/` | List or create datasets. |
| GET/PATCH/DELETE | `/datasets/{id}/` | Read, update or delete a dataset. |
| GET/POST | `/datasets/{id}/records/` | List or manually add records. |
| POST | `/datasets/{id}/import/` | Import JSON, JSONL or CSV (`multipart/form-data`). |
| GET/PATCH/DELETE | `/dataset-records/{id}/` | Read, update or delete one record. |
| GET | `/evaluation-metrics/` | List metrics this deployment can execute. |
| GET/POST | `/projects/{id}/evaluations/` | List or start evaluations. |
| GET | `/evaluations/{id}/` | Read run status, configuration and summaries. |
| GET | `/evaluations/{id}/results/` | Paginated per-case results; filters `model`, `status`. |
| POST | `/evaluations/{id}/rerun/` | Create a new run from the stored evaluation snapshot. |

### Observability

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{id}/observability/` | Project trace/latency/token/cost dashboard. |
| GET | `/projects/{id}/observability/traces/` | Filterable trace list. |
| GET | `/observability/traces/{trace_id}/` | Trace detail, linked request/response and spans. |

### Security scans and AI security testing

| Method | Path | Purpose |
|---|---|---|
| GET | `/security/checks/` | PII/injection/unsafe-output catalogue and limitations. |
| GET/POST | `/projects/{id}/security/scans/` | List or start a security scan. |
| GET | `/projects/{id}/security/` | Security dashboard. |
| GET | `/projects/{id}/security/findings/` | Filterable findings; filters `status`, `severity`, `category`, `check`, `scan`. |
| GET | `/projects/{id}/security/compare/` | Compare `baseline` and `current` scans. |
| GET | `/security-scans/{id}/` | Scan status, counts and summary. |
| GET | `/security-scans/{id}/findings/` | Findings for one scan. |
| POST | `/security-scans/{id}/rerun/` | Rerun the same scan target/configuration. |
| GET/PATCH | `/security-findings/{id}/` | Read or review a finding (`status`, `classification`, `note`). |
| GET | `/security-testing/catalog/` | Fixed attack cases, categories, criteria and limitations. |
| GET/POST | `/projects/{id}/security-testing/runs/` | List or start AI security test runs. |
| GET | `/projects/{id}/security-testing/` | AI security testing dashboard. |
| GET | `/projects/{id}/security-testing/compare/` | Compare `baseline` and `current` runs. |
| GET | `/projects/{id}/security-testing/history/` | Model-level run history. |
| GET | `/security-test-runs/{id}/` | Run status and summary. |
| GET | `/security-test-runs/{id}/results/` | Paginated results; filters `model`, `category`, `verdict`, `status`. |
| POST | `/security-test-runs/{id}/rerun/` | Create a new run from the same configuration. |
| GET | `/security-test-results/{id}/` | Full attack input, response, rationale and evidence. |

### Analytics and reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{id}/analytics/` | Workspace/project analytics dashboard. |
| GET | `/projects/{id}/analytics/models/` | Model performance comparison. |
| GET/POST | `/projects/{id}/analytics/reports/` | List or create report snapshots. |
| GET | `/analytics-reports/{id}/` | Read a report snapshot document. |
| GET | `/analytics-reports/{id}/export/?export_format=csv` | Download CSV export. |
| GET | `/analytics-reports/{id}/export/?export_format=pdf` | Download PDF export. |

### Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/` | Process + database liveness/readiness. |
| GET | `/health/worker/` | Redis broker status. |
| GET | `/health/worker/?probe=1` | Broker plus live Celery round trip. |

Health endpoints do not require authentication. They return `503` with
`status: "degraded"` when a dependency is unavailable.

## End-to-end curl example

The example uses shell variables. Replace UUIDs and model names with values from your
own responses. It assumes an Ollama provider reachable at `localhost:11434` and a pulled
model named `llama3.2`.

```bash
API=http://localhost:8000/api/v1

# 1. Register and save the access token.
TOKEN=$(curl -sS -X POST "$API/auth/register/" \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"Str0ng-Passw0rd!","display_name":"Demo"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['tokens']['access'])")

AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')

# 2. Create a workspace.
WORKSPACE_ID=$(curl -sS -X POST "$API/workspaces/" "${AUTH[@]}" \
  -d '{"name":"Demo workspace"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 3. Create a project.
PROJECT_ID=$(curl -sS -X POST "$API/projects/" "${AUTH[@]}" \
  -d "{\"workspace\":\"$WORKSPACE_ID\",\"name\":\"Support QA\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 4. Add a local Ollama provider.
PROVIDER_ID=$(curl -sS -X POST "$API/projects/$PROJECT_ID/providers/" "${AUTH[@]}" \
  -d '{"name":"Local Ollama","kind":"ollama","endpoint":"http://localhost:11434","settings":{}}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 5. Refresh the model catalogue.
curl -sS -X GET "$API/providers/$PROVIDER_ID/models/" "${AUTH[@]}"

# 6. Run a prompt.
curl -sS -X POST "$API/projects/$PROJECT_ID/executions/" "${AUTH[@]}" \
  -d "{
    \"system_prompt\":\"You are terse.\",
    \"user_prompt\":\"Say hello.\",
    \"parameters\":{\"max_tokens\":64},
    \"models\":[{\"provider\":\"$PROVIDER_ID\",\"model_id\":\"llama3.2\"}]
  }"

# 7. Create a dataset and add one record.
DATASET_ID=$(curl -sS -X POST "$API/projects/$PROJECT_ID/datasets/" "${AUTH[@]}" \
  -d '{"name":"Support QA","description":"Regression cases"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -sS -X POST "$API/datasets/$DATASET_ID/records/" "${AUTH[@]}" \
  -d '{"input":"What is 2+2?","expected_output":"4","context":["Two plus two equals four."]}'

# 8. Start an evaluation.
curl -sS -X POST "$API/projects/$PROJECT_ID/evaluations/" "${AUTH[@]}" \
  -d "{
    \"dataset\":\"$DATASET_ID\",
    \"metrics\":[\"exact_match\",\"token_f1\"],
    \"models\":[{\"provider\":\"$PROVIDER_ID\",\"model_id\":\"llama3.2\"}]
  }"
```

The evaluation endpoint returns immediately with a queued/running/completed status. Poll
`GET /evaluations/{id}/` and then read `GET /evaluations/{id}/results/`. Results are
paginated.

## Representative request and response bodies

### Create a workspace

```http
POST /api/v1/workspaces/
Authorization: Bearer <token>
Content-Type: application/json

{"name":"Acme AI","settings":{}}
```

```json
{
  "id": "9e6d7d6a-4b4b-4a4b-9b9b-6d6d6d6d6d6d",
  "name": "Acme AI",
  "owner": "2f4f4f3a-6f6f-4f4f-8f4f-4f4f4f4f4f4f",
  "settings": {},
  "role": "owner",
  "created_at": "2026-11-09T12:01:00Z",
  "updated_at": "2026-11-09T12:01:00Z"
}
```

### Create an Ollama provider

```http
POST /api/v1/projects/<project-id>/providers/
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Local Ollama",
  "kind": "ollama",
  "endpoint": "http://localhost:11434",
  "settings": {"temperature": 0.1}
}
```

```json
{
  "id": "d5a5a5a5-1111-4222-8333-444455556666",
  "project": "a1b2c3d4-1111-4222-8333-444455556666",
  "name": "Local Ollama",
  "kind": "ollama",
  "endpoint": "http://localhost:11434",
  "settings": {"temperature": 0.1},
  "connection_status": "untested",
  "connection_detail": "",
  "last_tested_at": null,
  "has_secret": false,
  "models": [],
  "created_at": "2026-11-09T12:05:00Z",
  "updated_at": "2026-11-09T12:05:00Z"
}
```

An API key is write-only. It is never present in a response, and `has_secret` only
indicates whether one is stored.

### Execute a comparison

```http
POST /api/v1/projects/<project-id>/executions/
Authorization: Bearer <token>
Content-Type: application/json

{
  "system_prompt": "You are terse.",
  "user_prompt": "Say hello.",
  "parameters": {"max_tokens": 64},
  "models": [
    {"provider": "<provider-id>", "model_id": "llama3.2"},
    {"provider": "<provider-id>", "model_id": "qwen2.5:3b"}
  ]
}
```

Selected response fields:

```json
{
  "id": "b1b1b1b1-2222-4333-8444-555566667777",
  "project": "a1b2c3d4-1111-4222-8333-444455556666",
  "mode": "compare",
  "system_prompt": "You are terse.",
  "user_prompt": "Say hello.",
  "parameters": {"max_tokens": 64},
  "status": "partial",
  "results": [
    {
      "position": 0,
      "provider_name": "Local Ollama",
      "provider_kind": "ollama",
      "model_id": "llama3.2",
      "content": "Hello.",
      "input_tokens": 12,
      "output_tokens": 2,
      "latency_ms": 240.5,
      "status": "succeeded",
      "error": null
    },
    {
      "position": 1,
      "provider_name": "Local Ollama",
      "provider_kind": "ollama",
      "model_id": "qwen2.5:3b",
      "content": "",
      "input_tokens": null,
      "output_tokens": null,
      "latency_ms": 8000.0,
      "status": "failed",
      "error": {
        "category": "timeout",
        "message": "The provider did not respond before the timeout."
      }
    }
  ]
}
```

### Import a dataset

```bash
curl -sS -X POST "http://localhost:8000/api/v1/datasets/$DATASET_ID/import/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@cases.jsonl" \
  -F "mode=append"
```

```json
{"imported": 25, "version": 2, "mode": "append"}
```

`mode` is `append` (default) or `replace`. Imports are all-or-nothing: a validation error
imports nothing and returns row-level errors. See [EVALUATION.md](EVALUATION.md) for the
file formats and limits.

### Start an evaluation

```http
POST /api/v1/projects/<project-id>/evaluations/
Authorization: Bearer <token>
Content-Type: application/json

{
  "dataset": "<dataset-id>",
  "metrics": ["exact_match", "token_f1", "answer_relevancy"],
  "models": [
    {"provider": "<provider-id>", "model_id": "llama3.2"}
  ],
  "parameters": {"temperature": 0.1},
  "judge": {
    "provider": "<provider-id>",
    "model_id": "llama3.2",
    "parameters": {"temperature": 0}
  }
}
```

Selected response fields:

```json
{
  "id": "c2c2c2c2-3333-4444-8555-666677778888",
  "project": "a1b2c3d4-1111-4222-8333-444455556666",
  "dataset": "d3d3d3d3-4444-4555-8666-777788889999",
  "dataset_name": "Support QA",
  "dataset_version": 2,
  "status": "queued",
  "metrics": ["exact_match", "token_f1", "answer_relevancy"],
  "total_cases": 25,
  "completed_cases": 0,
  "failed_cases": 0,
  "judge": {
    "provider": "<provider-id>",
    "provider_name": "Local Ollama",
    "model_id": "llama3.2"
  }
}
```

Judge-based metrics require a `judge`. Reference-only metrics must not include one. See
[EVALUATION.md](EVALUATION.md) for available metrics and their requirements.

### Read a trace

```bash
curl -sS "http://localhost:8000/api/v1/observability/traces/$TRACE_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

Selected response fields:

```json
{
  "id": "e4e4e4e4-5555-4666-8777-888899990000",
  "source": "playground",
  "role": "model",
  "status": "succeeded",
  "provider_name": "Local Ollama",
  "model_id": "llama3.2",
  "duration_ms": 240.5,
  "input_tokens": 12,
  "output_tokens": 2,
  "cost_status": "unavailable",
  "cost_detail": "No pricing is configured for ollama:llama3.2.",
  "request": {
    "kind": "playground",
    "system_prompt": "You are terse.",
    "user_prompt": "Say hello.",
    "parameters": {"max_tokens": 64}
  },
  "response": "Hello.",
  "spans": [
    {"name": "provider.prepare", "kind": "internal", "status": "ok"},
    {"name": "provider.generate", "kind": "client", "status": "ok"}
  ]
}
```

### Start a security scan

```http
POST /api/v1/projects/<project-id>/security/scans/
Authorization: Bearer <token>
Content-Type: application/json

{
  "target_type": "dataset",
  "target_id": "<dataset-id>",
  "checks": ["pii", "prompt_injection", "unsafe_output"],
  "config": {"pii_categories": ["email", "phone", "ssn"]},
  "blocking_enabled": false
}
```

```json
{
  "id": "f5f5f5f5-6666-4777-8888-999900001111",
  "target_type": "dataset",
  "target_label": "Support QA",
  "checks": ["pii", "prompt_injection", "unsafe_output"],
  "status": "queued",
  "total_items": 0,
  "scanned_items": 0,
  "finding_count": 0,
  "highest_severity": ""
}
```

### Start an AI security test run

```http
POST /api/v1/projects/<project-id>/security-testing/runs/
Authorization: Bearer <token>
Content-Type: application/json

{
  "models": [{"provider": "<provider-id>", "model_id": "llama3.2"}],
  "categories": ["prompt_injection", "jailbreak"],
  "parameters": {"temperature": 0}
}
```

You may send `cases` instead of `categories`. Only reviewed catalogue keys are accepted;
arbitrary attack prompts and external targets are rejected. See
[SECURITY.md](SECURITY.md) for the case catalogue and result semantics.

### Create an analytics report

```http
POST /api/v1/projects/<project-id>/analytics/reports/
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Weekly quality review",
  "from": "2026-11-01",
  "to": "2026-11-09",
  "provider": "<provider-id>",
  "sections": ["overview", "performance", "evaluations", "costs", "security", "trends"]
}
```

The response contains a frozen `document` snapshot. Download it with
`/analytics-reports/{id}/export/?export_format=csv` or `...=pdf`. Reports do not refresh
when new activity arrives.

## Permissions in the API

- All endpoints except `/health/`, `/health/worker/`, registration and login require
  authentication.
- Viewers can read workspace resources.
- Members can create project content and can update projects/datasets they created;
  admins/owners can update any project/dataset in the workspace. Members can run security
  tests/scans and review findings.
- Admins can manage workspace members and provider configuration.
- Owners have the highest role and can delete the workspace/its configuration.
- Non-members receive `404` for project-scoped resources.

The authoritative checks are service-level and are covered by permission tests. See
[SECURITY.md](SECURITY.md) for the complete matrix.
