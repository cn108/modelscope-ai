# ModelScope AI

ModelScope AI is a self-hosted platform for comparing AI models and evaluating their
quality, safety and operational behaviour. It gives a team a workspace-scoped place to
configure providers, run prompts, build datasets, execute repeatable evaluations, inspect
traces, scan for common security risks, run controlled AI security tests and export
analytics reports.

The application is a Django REST API plus an Angular single-page frontend. PostgreSQL is
the source of truth, Redis and Celery run asynchronous work, and model access is isolated
behind provider adapters.

> **Project status:** the product milestones and hardening work are implemented and the
> automated suite is green. Live Z.ai verification still requires an operator API key,
> and no production host/TLS target was supplied. See [HANDOVER.md](docs/HANDOVER.md) for
> evidence, remaining operational steps and the honest production-readiness assessment.

## Contents

- [Features](#features)
- [Product tour and workflows](#product-tour-and-workflows)
- [Architecture](#architecture)
- [Technology](#technology)
- [Prerequisites](#prerequisites)
- [Quick start with Docker Compose](#quick-start-with-docker-compose)
- [Native development](#native-development)
- [First-use walkthrough](#first-use-walkthrough)
- [Provider support](#provider-support)
- [Configuration](#configuration)
- [API and OpenAPI](#api-and-openapi)
- [Tests](#tests)
- [Documentation](#documentation)
- [Operational notes](#operational-notes)
- [Known limitations](#known-limitations)

## Features

- Email/password accounts with rotating JWT refresh tokens, profile preferences,
  password changes and account/workspace audit views.
- Workspaces with owner, admin, member and viewer roles; workspace-scoped projects,
  member management, JSON export and owner-only deletion.
- Project provider configuration for Z.ai (cloud), Ollama (local) and LM Studio (local).
- Settings page for account, workspace, team, providers, security, audit and About,
  backed by real APIs (no decorative controls).
- Playground runs against one model or a side-by-side comparison of two models.
- Saved prompts with append-only versions and restore.
- Datasets with manual record management and validated JSON, JSONL and CSV imports.
- Evaluation runs with reference/judge metrics (including factual correctness, context
  precision/recall and toxicity), per-case results, metric versioning, human review with
  disagreement analysis, model comparison, progress and repeatable reruns.
- Execution traces, span trees, latency/token summaries, optional OTLP export, daily
  rollups and configurable raw-trace retention.
- Heuristic security scans for PII, prompt injection and unsafe output, with redacted
  evidence, review status, history and scan comparison.
- Controlled AI security testing with a fixed catalogue of reviewed attack cases and
  deterministic pass/fail/inconclusive classification.
- Workspace/project analytics, model performance comparison and reproducible CSV/PDF
  report snapshots.

## Product tour and workflows

The screenshots below were captured from the Docker Compose stack running against a local
Ollama model and a seeded acceptance workspace. They show real stored executions,
evaluation cases, security findings and trace records; no production or personal data is
included.

### Dashboard and platform health

![Dashboard showing workspace, project, team and API health cards](docs/screenshots/01-dashboard.png)

After sign-in the dashboard calls the health endpoint and the workspace API, then loads
projects and members for every workspace the signed-in user belongs to. The cards are
derived from those responses: workspace/project/member counts, the workspace breakdown and
the current database/service health. Nothing on this page is hard-coded placeholder data.

### Playground: run one model or compare two

![Playground showing a completed Ollama response, latency, tokens and saved prompt versions](docs/screenshots/02-playground.png)

Choose a project, provider and model, then edit the system/user prompts and temperature or
token limit. **Single model** sends one request; **Compare two** sends the same prompt to two
models. The backend creates an execution, snapshots the prompt version and parameters, and
stores one result per model, so a failure on one side does not discard the other response.
The response card reports provider latency and token usage; cost appears only when pricing
is configured and the provider reports both token counts. Every run is kept in history and
can be rerun from its original inputs.

### Versioned datasets and repeatable evaluations

![Dataset editor showing a versioned test set, JSONL import and manual records](docs/screenshots/03-datasets.png)

A dataset can be edited manually or imported from JSON, JSONL or CSV. Each change creates a
new dataset version, so an evaluation can keep using the exact snapshot it started with.

![Evaluation result showing per-case scores, expected answer and human review controls](docs/screenshots/04-evaluations.png)

An evaluation selects the dataset snapshot, up to five models and the available metrics.
The API enqueues a Celery task; the worker calls each provider, scores every case and stores
per-case results together with the metric versions. The results view exposes the model
response, reference answer, retrieval context, metric scores and a human-review label so a
reviewer can record disagreement without changing the original detection.

### Security scans and reviewed findings

![Security finding detail showing redacted evidence, severity and review history](docs/screenshots/05-security-findings.png)

A scan runs the selected heuristic checks over a dataset, prompt or execution record. The
worker detects PII, prompt-injection patterns and unsafe output, redacts the evidence before
it is stored, and records severity, status and the rule that matched. The detail view shows
why the item was flagged and keeps an append-only review history; the raw email in the test
record is displayed as `[REDACTED]`, not copied into the finding.

### AI security testing with recorded evidence

![AI security test result showing the attack input, actual model response and classification](docs/screenshots/06-ai-security-testing.png)

AI Testing uses a fixed catalogue of reviewed attack cases instead of arbitrary prompts.
Select the configured models and cases, and the worker sends the reviewed system context and
attack input through the provider adapters, records the actual response, and applies
deterministic pass/fail/inconclusive criteria. The evidence drawer preserves the system
context, attack input, model response, matched rule and recommended mitigation. A pass is
recorded as evidence, not as a guarantee that the model is secure.

### Analytics, reports and trace inspection

![Analytics showing model calls, token usage, latency, evaluation and security activity](docs/screenshots/07-analytics.png)

Analytics is computed from stored executions, traces, evaluations and security findings,
not from a separate metrics store. Filters narrow the data by date, provider, model and
source; costs remain **Unavailable** unless explicit token pricing is configured and the
provider reports usage. A report snapshot can be generated and downloaded as CSV or PDF.

![Trace detail showing the request, response, latency, token counts and trace metadata](docs/screenshots/08-observability.png)

Observability records a trace and span tree for each model call, with latency and token
summaries. The detail view exposes the request, response and stored metadata, and traces can
optionally be exported to an OTLP/HTTP collector. Daily rollups and retention are handled by
Celery Beat when enabled.

## Architecture

```mermaid
flowchart LR
    Browser[Angular SPA] -->|/api/v1| API[Django REST API]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis)]
    API -->|playground calls| Providers[Z.ai / Ollama]
    Redis --> Worker[Celery worker]
    Redis --> Beat[Celery beat]
    Worker --> DB
    Worker --> Providers
    API -. optional OTLP .-> OTel[OpenTelemetry collector]
    Worker -. optional OTLP .-> OTel
```

The backend is deliberately a modular monolith. `apps/` contains domain modules,
`integrations/` contains provider, evaluation, telemetry, security and reporting
boundaries, and `common/` contains cross-cutting audit, encryption, health and API
helpers. The detailed component map and request flows are in
[ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology

| Layer | Technology |
|---|---|
| Frontend | Angular 20 standalone components, TypeScript, Tailwind CSS 3 |
| Backend | Python 3.12, Django 5.2, Django REST Framework 3.18 |
| Authentication | SimpleJWT with Argon2 password hashing |
| Data | PostgreSQL 16, UUID primary keys |
| Async work | Celery 5 with Redis 7 |
| AI evaluation | Built-in reference metrics; optional DeepEval judge metrics |
| Telemetry | OpenTelemetry SDK with optional OTLP/HTTP export |
| Packaging | Docker Compose, Gunicorn, nginx |
| Tests | pytest/pytest-django, Angular Karma/Jasmine, Playwright |

## Prerequisites

For the Docker path:

- Docker Desktop or Docker Engine with the Compose plugin.
- About 4 GB of free memory for PostgreSQL, Redis, Django, Celery and the frontend.
- Python 3.12 only if you want to generate a Fernet key outside the backend container.
- Ollama and a downloaded model if you want to run local inference.

For native development:

- Python 3.12.
- Node.js 20+ (CI and the Docker frontend image use Node 22).
- PostgreSQL 16 and Redis 7. The Compose stack can provide both while Django and Angular
  run natively.
- Chrome/Chromium for the Karma test runner.

## Quick start with Docker Compose

Run these commands from the repository root.

### 1. Create the environment file

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```dotenv
DJANGO_SECRET_KEY=<long random value>
POSTGRES_PASSWORD=<strong local password>
PROVIDER_SECRET_KEYS=<one Fernet key>
```

Generate the Django secret with the Python standard library:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Generate a Fernet key after the backend dependencies are installed, or from the backend
container after its first build:

```bash
# From an activated backend virtual environment:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Or, Docker-only after the image has been built once:
docker compose -f infrastructure/docker-compose.yml --env-file .env run --rm --no-deps \
  backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`PROVIDER_SECRET_KEYS` is required before an API key can be stored for Z.ai. Provider
credentials are encrypted with the first key; all configured keys can decrypt, which
supports rotation. Never commit `.env`.

### 2. Start the stack

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env up --build -d
```

The backend container applies migrations before Gunicorn starts. Check service state:

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env ps
```

### 3. Verify health

```bash
curl -fsS http://localhost:8000/api/v1/health/
curl -fsS "http://localhost:8000/api/v1/health/worker/?probe=1"
```

The first endpoint reports database connectivity. The second checks the Redis broker and,
with `?probe=1`, performs a live Celery round trip through the worker. A degraded result
is reported as HTTP 503 rather than a false `ok`.

### 4. Open the application

| Surface | URL |
|---|---|
| Angular application | <http://localhost:4200> |
| Django API root | <http://localhost:8000/api/v1/> |
| Swagger UI | <http://localhost:8000/api/docs/> |
| OpenAPI schema | <http://localhost:8000/api/schema/> |
| Django admin | <http://localhost:8000/admin/> |

Create the first account from the registration screen. No seeded administrator account
exists; after registering, create a workspace from the workspace screen (the creator
becomes its owner).

### 5. Useful Compose commands

```bash
# Follow all logs
docker compose -f infrastructure/docker-compose.yml --env-file .env logs -f

# Follow the worker only
docker compose -f infrastructure/docker-compose.yml --env-file .env logs -f worker

# Run Django management commands
docker compose -f infrastructure/docker-compose.yml --env-file .env exec backend \
  python manage.py check

# Stop the stack without deleting PostgreSQL/Redis volumes
docker compose -f infrastructure/docker-compose.yml --env-file .env down

# Stop and delete the local database/cache volumes (destructive)
docker compose -f infrastructure/docker-compose.yml --env-file .env down -v
```

The named volumes are `postgres_data` and `redis_data`. Do not use `down -v` if you need
the local data.

## Native development

The Compose stack can provide PostgreSQL and Redis while Django and Angular run on the
host.

### 1. Start dependencies

```bash
cp .env.example .env   # first time only
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d db redis
```

The example `.env` uses `POSTGRES_HOST=localhost` and `REDIS_URL=redis://localhost:6379/0`
for native runs. Compose overrides those values with the internal service names for its
own containers.

### 2. Backend

```bash
python -m venv backend/.venv

# macOS/Linux
source backend/.venv/bin/activate
# Windows PowerShell
# backend\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r backend/requirements/dev.txt

cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Start the worker in a second terminal:

```bash
cd backend
celery -A config worker --loglevel=INFO
```

Start the scheduler only if you need daily observability rollups/retention:

```bash
cd backend
celery -A config beat --loglevel=INFO
```

### 3. Frontend

```bash
cd frontend
npm ci
npm start
```

Angular serves on <http://localhost:4200> and proxies `/api` to
`http://localhost:8000` via `frontend/proxy.conf.json`.

### 4. Run checks

```bash
cd backend
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python -m pytest

cd ../frontend
npm test -- --watch=false --browsers=ChromeHeadless
npm run build
```

Backend tests use SQLite, eager Celery and a local-memory cache. That makes unit/API tests
hermetic but does **not** verify PostgreSQL, Redis or a real worker. Use the Compose
stack and the manual acceptance procedure in [TESTING.md](docs/TESTING.md) for that.

## First-use walkthrough

1. **Register** at `/register`; the account is signed in immediately.
2. **Create a workspace** from the workspace screen. The creator becomes owner.
3. **Create a project** inside the workspace.
4. **Add a provider** on the project's provider screen:
   - Z.ai requires an API key.
   - Ollama requires a reachable local endpoint and a pulled model.
5. **Test the connection** and refresh the model list.
6. **Run a prompt** in the playground. Select one model, or two for comparison.
7. **Save a prompt** if you want reusable, versioned system/user prompts.
8. **Create a dataset** and add records or import a JSON/JSONL/CSV file.
9. **Start an evaluation**, choose a dataset, up to five models and the available
   metrics. Inspect per-case results and aggregate scores.
10. **Inspect traces** in the project observability view.
11. **Run a security scan** against a dataset, prompt or execution record.
12. **Run an AI security test** against configured models and reviewed attack cases.
13. **Open analytics** to compare models and generate a CSV/PDF report snapshot.

## Provider support

| Provider | Status | Notes |
|---|---|---|
| Z.ai | Supported | Fixed base URL `https://api.z.ai/api/paas/v4`; API key required. Live verification still needs an operator-supplied key. |
| Ollama | Supported | Local Ollama HTTP API, standard local port 11434. Live-tested with Ollama `0.40.13` and `llama3.2:1b`. |
| LM Studio | Supported | Local OpenAI-compatible API on port 1234; optional API key. Covered by adapter/endpoint tests; no live LM Studio instance was available. |
| Generic OpenAI-compatible API | **Not implemented** | Only the Z.ai adapter uses an OpenAI-compatible cloud API today. |
| Hugging Face | **Not implemented** | No adapter is present. |

Provider setup, endpoint rules, credential rotation and troubleshooting are in
[PROVIDERS.md](docs/PROVIDERS.md).

## Configuration

Django loads `.env` from the repository root. Compose reads the same file through
`env_file` and overrides container-internal hosts. The full operator reference is in
[OPERATIONS.md](docs/OPERATIONS.md); the main variables are:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | empty in base; dev fallback | JWT signing and Django cryptographic signing. Required in production. |
| `DJANGO_DEBUG` | `true` in dev | Development debug flag. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated Host header allow-list. |
| `LOG_LEVEL` | `INFO` | Root log level. |
| `POSTGRES_DB` | `modelscope` | Database name. |
| `POSTGRES_USER` | `modelscope` | Database user. |
| `POSTGRES_PASSWORD` | empty | Database password; Compose requires it for the `db` service. |
| `POSTGRES_HOST` | `db` | `localhost` for native runs; Compose uses `db`. |
| `POSTGRES_PORT` | `5432` | PostgreSQL port. |
| `DATABASE_ENGINE` | `postgresql` | Set `sqlite` only for local/unit-test convenience. |
| `REDIS_URL` | `redis://redis:6379/0` | Cache and default Celery URLs. |
| `CELERY_BROKER_URL` | `REDIS_URL` | Optional broker override. |
| `CELERY_RESULT_BACKEND` | `REDIS_URL` | Optional result-backend override. |
| `JWT_ACCESS_MINUTES` | `15` | Access-token lifetime; refresh tokens last 7 days and rotate. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:4200,http://localhost:8080` | Explicit browser-origin allow-list. |
| `RATE_LIMIT_LOGIN` | `10/min` | Login attempts per client address and hashed email. |
| `RATE_LIMIT_MODEL_CALL` | `30/min` | Playground/provider test/model-call endpoints. |
| `RATE_LIMIT_EVALUATION_CREATE` | `30/hour` | Evaluation/rerun creation. |
| `PROVIDER_TIMEOUT_SECONDS` | `60` | Per-request provider timeout. |
| `PROVIDER_MAX_RETRIES` | `2` | Retries for transient provider failures. |
| `PROVIDER_MAX_CONCURRENCY` | `8` | In-flight provider calls per worker process. |
| `BACKUP_ENABLED` | `false` | Daily PostgreSQL backup task. |
| `BACKUP_DIR` | `backups` | Backup directory inside the container. |
| `BACKUP_RETENTION_DAYS` | `30` | Delete older backups. |
| `PROVIDER_SECRET_KEYS` | empty | Comma-separated Fernet keys, current first. Required to store provider secrets. |
| `EVALUATION_JUDGE_METRICS_ENABLED` | `true` | Expose DeepEval judge metrics when DeepEval is installed. |
| `OTEL_TRACING_ENABLED` | `true` | Create in-process OTel spans. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | Optional OTLP/HTTP trace endpoint. |
| `EXECUTION_PRICING` | empty | JSON pricing map keyed by `<kind>:<model>`; no built-in prices. |
| `OBSERVABILITY_ROLLUP_ENABLED` | `true` | Enable daily trace rollups and the maintenance schedule. |
| `OBSERVABILITY_TRACE_RETENTION_DAYS` | `0` | `0` keeps raw traces forever; positive values purge after a successful rollup. |
| `SECURITY_MAX_SCAN_ITEMS` | `10000` | Per-scan item cap. |
| `SECURITY_TEST_MAX_MODELS` | `5` | Maximum models per AI security test run. |
| `SECURITY_TEST_MAX_RESULTS` | `120` | Maximum case/model results per run. |
| `SECURE_SSL_REDIRECT` | `true` in production | Redirect HTTP to HTTPS when production settings are used. |

`EXECUTION_PRICING` example:

```dotenv
EXECUTION_PRICING={"zai:glm-5.3":{"input_per_million":"0.60","output_per_million":"2.20","currency":"USD"}}
```

Costs remain unavailable unless both token counts are provider-reported and a matching
price entry exists.

## API and OpenAPI

The API is versioned under `/api/v1/`. Authentication uses a Bearer access token:

```http
Authorization: Bearer <access token>
```

The generated OpenAPI schema and interactive documentation are always the source of
truth for request fields:

- Swagger UI: `http://localhost:8000/api/docs/`
- Schema: `http://localhost:8000/api/schema/`

A short end-to-end curl sequence, endpoint map, pagination conventions and example
requests/responses are in [API.md](docs/API.md).

## Tests

```bash
cd backend
python -m pytest
```

Last verified: **176 passed**.

```bash
cd frontend
npm test -- --watch=false --browsers=ChromeHeadless
npm run build
```

Last verified: **23 specs passed**, lint, typecheck and production build succeeded. CI
runs backend lint/mypy/pip-audit, frontend lint/typecheck/npm audit, both test suites,
production builds, and a full Docker/Ollama Playwright journey on every push and pull
request.

With the Docker stack running and Ollama reachable, run the full browser acceptance
journey:

```bash
cd frontend
npm run e2e
```

See [TESTING.md](docs/TESTING.md) for the journey's prerequisites, coverage and current
gaps.

## Documentation

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, request flows, trust boundaries, extension points. |
| [API.md](docs/API.md) | Auth, endpoint map, pagination/errors and curl examples. |
| [DATA-MODEL.md](docs/DATA-MODEL.md) | Entity relationship diagram, key invariants and migration notes. |
| [PROVIDERS.md](docs/PROVIDERS.md) | Z.ai, Ollama and LM Studio setup, endpoint rules, retries, secret rotation, unsupported providers. |
| [EVALUATION.md](docs/EVALUATION.md) | Dataset formats, metric definitions/versions, judge setup, human review, limitations, reproducibility. |
| [SECURITY.md](docs/SECURITY.md) | Roles, tenant isolation, secret handling, privacy/retention, scan limitations. |
| [OPERATIONS.md](docs/OPERATIONS.md) | Configuration, health, migrations, backups/restore, production checklist. |
| [TESTING.md](docs/TESTING.md) | Automated checks and manual end-to-end/hardening acceptance. |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common startup, provider, Celery, frontend and test failures. |
| [HANDOVER.md](docs/HANDOVER.md) | Milestone status, evidence, blockers and remaining acceptance work. |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Original milestone plan, scope decisions and verification status. |
| [ADR-0001](docs/adr/ADR-0001-modular-monolith.md) | Modular monolith and async worker decision. |
| [ADR-0002](docs/adr/ADR-0002-version-pins.md) | Framework version pins. |
| [ADR-0003](docs/adr/ADR-0003-secret-encryption.md) | Provider secret encryption and rotation. |
| [ADR-0004](docs/adr/ADR-0004-milestone-9-scope.md) | AI security testing scope and the hardening boundary. |
| [ADR-0005](docs/adr/ADR-0005-provider-scope.md) | Z.ai/Ollama provider scope and deferred adapters. |

## Operational notes

- **Migrations:** run `python manage.py migrate` before starting a new API/worker version.
  Back up the database before migrations that change existing data.
- **Backups:** `python manage.py backup_database` creates a retained custom-format dump;
  set `BACKUP_ENABLED=true` for the daily Celery Beat task. Retain
  `PROVIDER_SECRET_KEYS` separately: a database restore without the matching encryption
  key cannot decrypt provider secrets. Copy backups off-host.
- **Export/delete:** workspace admins can export workspace JSON or delete the workspace
  from Settings → Security. Workspace deletion cascades to projects and their records.
- **Redis:** losing Redis can drop queued Celery tasks. Persisted results remain in
  PostgreSQL; re-run interrupted jobs after restoring service.
- **Retention:** `OBSERVABILITY_TRACE_RETENTION_DAYS` affects raw traces only. Execution
  and evaluation records remain until explicitly deleted.
- **Production:** use `infrastructure/docker-compose.prod.yml` plus a TLS-terminating
  proxy, off-host backups and monitoring. See [OPERATIONS.md](docs/OPERATIONS.md).

## Known limitations

- Live Z.ai verification requires an operator API key that was not supplied; the adapter
  is tested against a deterministic transport stub.
- LM Studio has adapter and endpoint coverage but no live instance was available.
- Generic OpenAI-compatible providers and Hugging Face are not implemented.
- Security scans and AI security tests are heuristic detection aids, not proof of safety.
- The Angular client stores JWT tokens in `localStorage`. This is a known residual risk;
  short access-token lifetimes, refresh rotation/blacklisting and a strict CSP reduce the
  impact, but httpOnly cookies would be the stronger design. See
  [SECURITY.md](docs/SECURITY.md).
- Human review captures multiple reviewers and disagreement; it is not a complete
  annotation queue or sampling workflow.
- The production profile is configuration- and image-validated locally, but no production
  TLS/host target was supplied for a live deployment.

For the full gap list and recommended order of work, see [HANDOVER.md](docs/HANDOVER.md).
