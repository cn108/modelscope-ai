# Troubleshooting

## Docker and Compose

### `Cannot connect to the Docker daemon`

The Docker CLI is installed but the daemon/socket is unavailable. Start Docker Desktop or
the Docker service, then verify:

```bash
docker info
```

The live Compose acceptance passed on Docker Desktop `29.9.2` on 2026-11-09. If the daemon
is unavailable, start Docker Desktop and retry; the application unit tests do not require
Docker. See [HANDOVER](HANDOVER.md#verification-evidence) for the evidence.

### `POSTGRES_PASSWORD must be set in .env`

Compose requires the database password. Copy the template and set a value:

```bash
cp .env.example .env
# edit POSTGRES_PASSWORD
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d db
```

### Backend exits during migration/startup

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env logs backend
```

Common causes: PostgreSQL not yet healthy, wrong password, a migration error, or missing
`DJANGO_SECRET_KEY` in a production settings module. The Compose backend waits for the
database healthcheck, but a failing migration still stops Gunicorn.

### Port already in use

The stack publishes `8000` (backend) and `4200` (frontend). Stop the conflicting process
or change the host-side mapping in `infrastructure/docker-compose.yml`. Do not change the
container-to-container service names without updating the frontend nginx config.

## Database and migrations

### `relation ... does not exist`

Migrations have not been applied to the database being used.

```bash
cd backend
python manage.py migrate
```

If you are running tests, remember that `config.settings.test` uses a fresh in-memory
SQLite database; it will not show data from your development PostgreSQL database.

### `makemigrations --check` reports changes

A model changed without a migration. Create and review a migration:

```bash
cd backend
python manage.py makemigrations
python manage.py migrate
```

Do not edit an already-applied migration in a shared environment.

### SQLite works but PostgreSQL fails

The test suite uses SQLite for speed and isolation. PostgreSQL-specific constraints,
indexes, case sensitivity, JSON behavior and concurrency are not covered. Reproduce with
the Compose PostgreSQL service and inspect the backend logs before assuming an application
bug.

## Redis/Celery

### Health says worker/broker degraded

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env ps
docker compose -f infrastructure/docker-compose.yml --env-file .env logs redis
docker compose -f infrastructure/docker-compose.yml --env-file .env logs worker
```

Check `REDIS_URL`, the broker URL overrides, and that the worker is running. The health
probe intentionally returns `503` when it cannot verify the dependency.

### Evaluation/scan/test stays queued

- Confirm the worker is running and connected to the same Redis database.
- Inspect worker logs for task import or database errors.
- Confirm the API and worker use the same `DJANGO_SETTINGS_MODULE`, database and secret
  configuration.
- If Redis lost the queued task, rerun the job from the UI/API after recovery. There is no
  automatic retry/backoff policy for provider failures.

### `queue_unavailable`

The API could not enqueue work because the broker was unreachable. Restore Redis/worker
and create or rerun the job. The run is marked failed rather than silently disappearing
where the service supports that status.

## Authentication and permissions

### `401 Unauthorized`

- Missing/expired Bearer token. Log in again.
- Refresh tokens rotate; reusing an old refresh token is rejected by design.
- If the Django `SECRET_KEY` changed, existing JWTs are invalid.

### `403 Forbidden`

The caller is a workspace member but lacks the required role. Providers and workspace
member management require admin/owner; project/dataset edits by members are limited to
resources they created. See [SECURITY.md](SECURITY.md).

### `404 Not Found` for a resource that exists

Cross-tenant access is intentionally reported as `404` to avoid disclosing existence.
Check that the user is a member of the resource's workspace. A genuinely missing ID also
returns `404`.

### CORS error in the browser

Set `CORS_ALLOWED_ORIGINS` to the exact frontend origin, including scheme and port. The
defaults are `http://localhost:4200,http://localhost:8080`. Restart the backend after
changing it. CORS credentials are disabled; the SPA uses the Authorization header.

### Login works but API calls fail after a while

Access tokens expire after 15 minutes by default. The current Angular client does not
automatically refresh on a 401; log in again. Moving to refresh-on-401 is a known
frontend limitation.

## Provider setup

### `PROVIDER_SECRET_KEYS is not configured`

Set a Fernet key in `.env` and restart the API/worker:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The key must be a valid Fernet key. Multiple keys are comma-separated, current first.

### `Secret could not be decrypted with any configured key`

The key that encrypted the secret is no longer present, or the database was restored
without its key. Restore the old key or re-enter the provider API key. Do not remove old
keys until all secrets have been re-encrypted.

### Ollama endpoint rejected

The validator only accepts loopback/host-gateway hosts, port `11434`, no credentials/query,
and an empty or `/api` path. Use:

```text
http://localhost:11434
http://host.docker.internal:11434
```

LM Studio's usual `http://localhost:1234/v1` is not supported. See
[PROVIDERS.md](PROVIDERS.md).

### Ollama unreachable from Compose

- Ensure Ollama is running.
- Start it with `OLLAMA_HOST=0.0.0.0:11434` on a trusted network if Docker must reach it.
- Check the host firewall and that `host.docker.internal` resolves in the container.
- Try the provider connection test and inspect the sanitized detail.

### Z.ai test fails

Check the API key outside the app, outbound HTTPS access to `https://api.z.ai/api/paas/v4`,
and provider status. The app records a sanitized error; it does not echo the key.

### Model appears in the list but execution fails

The model must be served by the provider under that exact model ID. Refreshing
`/providers/{id}/models/` updates the catalogue; for Z.ai only the explicit `glm-5.3` and
`glm-5.3-flash` entries are available. AI security tests additionally require the model to
exist as a `ModelConfig` row for the provider.

## Evaluation

### `This metric needs an expected answer`

Reference metrics (`exact_match`, `contains_match`, `token_f1`) need
`expected_output` on the dataset record. Add it or choose a metric that does not require
it.

### `This metric needs retrieval context`

`faithfulness` and `contextual_relevancy` need `context` on each record.

### `This metric needs a judge model`

Select a judge provider/model for any judge-based metric. The judge must belong to the
same project. A judge supplied for reference-only metrics is rejected.

### Judge scores are missing/errored

DeepEval requires the judge model to return schema-valid structured output. A
non-compliant judge response is stored as a per-metric error, not a pass. Try a stronger
judge model or disable judge metrics with `EVALUATION_JUDGE_METRICS_ENABLED=false` and
restart.

### Evaluation never completes

Check worker logs and the evaluation's `error`/`status`. Provider timeouts and malformed
provider responses are stored per result; queue/broker failures mark the run failed. The
worker may need restarting.

## Datasets

### Import rejected with row errors

Imports are all-or-nothing. Check:

- extension is `.json`, `.jsonl`, `.ndjson` or `.csv`;
- JSON is an array or `{"records":[...]}`;
- CSV has an `input` header and only `input`, `expected_output`, `context`, `metadata`;
- context is a string, list of strings, or `||`-separated in CSV;
- metadata is a JSON object;
- limits: 500 records, 20,000 chars input/expected, 60,000 chars context, 4 KB metadata.

Nothing is imported until every row is valid.

### Dataset version changes unexpectedly

Any record create/update/delete/import increments the version by design. Metadata edits
to the dataset name/description do not. Old evaluation results retain their copied record
text, so they remain immutable.

## Observability

### No traces appear

- Confirm tracing is enabled (`OTEL_TRACING_ENABLED` controls OTel spans; database traces
  are created by the application paths).
- Run a playground/evaluation call; traces are created per model/judge call.
- Check the worker logs for trace persistence errors (telemetry failures are logged but do
  not break the user-visible call).

### Traces never disappear

`OBSERVABILITY_TRACE_RETENTION_DAYS=0` means keep forever. Set a positive number and run
the maintenance task/`purge_traces`. Retention only deletes raw traces; executions,
evaluations, datasets and findings are separate records.

### Cost is missing

Cost requires both provider-reported token counts and a matching explicit
`EXECUTION_PRICING` entry. Local models normally have no pricing, so cost is
`unavailable`, not zero.

## Frontend

### Blank page or API 404 after refresh

The nginx config uses `try_files ... /index.html` for SPA routing. If running a custom
static server, configure the same fallback. Confirm the frontend build output is the one
being served.

### Angular dev server cannot reach the API

`frontend/proxy.conf.json` proxies `/api` to `http://localhost:8000`. Make sure Django is
running on that port. In Compose, nginx proxies `/api/` to the `backend` service.

### Karma cannot find Chrome

Install Chrome/Chromium or set `CHROME_BIN` to its executable. CI uses ChromeHeadless; a
local headless environment without Chrome will fail before running specs.

### Frontend build fails on memory/bundle budget

The production build enforces Angular budgets. Check the first error; do not raise budgets
just to hide a large dependency without investigating it.

## Security scans and AI tests

### A clean scan says no findings but I expected one

Detection is heuristic and pattern-based. Unusual PII formats, encoded/split prompt
injection, novel jailbreaks and context-dependent unsafe output can be missed. A clean
scan is not proof of safety. Review the scan's limitations and use AI security tests for
model behavior.

### AI security test is inconclusive

The provider may have errored, returned an empty/ambiguous response, or failed the
canary/detector criteria. Inconclusive is not a pass. Inspect the stored response and
provider error, then rerun after fixing connectivity/configuration.

### AI security test rejects my model

The model must be a configured `ModelConfig` row for a project provider. Refresh the
provider model list first. Only reviewed case/category keys are accepted; arbitrary attack
prompts are intentionally rejected.

## Reports

### Report export returns 400

Use `?export_format=csv` or `?export_format=pdf`. `format` is reserved by DRF content
negotiation and is not the selector.

### Report numbers differ from current data

Reports are snapshots. They intentionally do not refresh when new executions, findings or
evaluations arrive. Create a new report for the current period.

## Tests and CI

### Backend tests pass locally but CI fails

CI uses Python 3.12, Node 22 and a clean install. Check `requirements/dev.txt`, the
lockfile and whether a test depends on local `.env` values or data. Tests should use
`config.settings.test` and fixtures, not the developer's database.

### `makemigrations --check` fails in CI

Commit the missing migration. Do not suppress the check.

### Frontend tests pass locally but fail in CI

Check ChromeHeadless availability, Node version, and whether the test relies on a local
proxy/backend. Karma specs should mock HTTP.

## Still stuck

Collect:

- the exact request/response (redact tokens and keys);
- backend/worker logs around the trace ID;
- `docker compose ps` and health output;
- the application commit and whether the stack is native or Compose;
- reproduction steps and expected vs actual behavior.

Do not paste provider keys, JWTs, customer data or full prompts into a public issue.
