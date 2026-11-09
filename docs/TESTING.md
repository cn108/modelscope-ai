# Testing guide

The repository has automated backend and frontend suites plus a manual acceptance
procedure for the Docker/PostgreSQL/Redis stack. The manual procedure is required because
the unit suite uses SQLite and eager Celery.

## Automated checks

Run from the repository root unless noted.

### Backend

```bash
cd backend
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python -m pytest
```

Last verified on commit `47cb078` (2026-11-09): **159 tests passed**. The suite uses
`config.settings.test`: SQLite in memory, eager Celery, local-memory cache and no provider
keys. It covers:

- auth registration/login/refresh rotation, password hashing and token rejection;
- workspace/project RBAC, cross-tenant 404s and audit events;
- provider secret encryption, write-only API behavior, endpoint SSRF allow/deny and
  redirect refusal;
- playground success, partial comparison failure, validation and duplicate-model
  rejection;
- dataset CRUD/import validation/versioning and record ownership rules;
- evaluation queuing, per-case results, metrics, judge configuration and reruns;
- trace/span persistence, pricing honesty, rollups and retention;
- security detector behavior, redacted evidence, finding review and scan comparison;
- AI security test execution, pass/fail/inconclusive classification, comparison and
  permissions;
- analytics aggregation, report snapshots, CSV/PDF exports and filters;
- health degradation when dependencies are unavailable.

### Frontend

```bash
cd frontend
npm test -- --watch=false --browsers=ChromeHeadless
npm run build
```

Last verified: **23 specs passed**, production build succeeded.

### Browser E2E (Playwright)

The full acceptance journey runs in Chromium against the live Docker stack. It needs the
frontend on <http://localhost:4200>, the API on <http://127.0.0.1:8000>, a running worker
and a reachable Ollama endpoint with `llama3.2:1b` pulled. The test talks to the same
database the stack uses, so point it at a disposable environment.

```bash
cd frontend
npx playwright install chromium   # once per machine
npm run e2e                       # headless full journey
npm run e2e:headed                # visible browser
npm run e2e:report                # open the HTML report after a failure
```

Set `E2E_BASE_URL` to target another frontend origin. The config reuses an already-running
server, so it does not start or stop the Docker services. A run creates a unique
`e2e-<suffix>@example.com` account and its own workspace, project, provider, dataset, prompt
and report, then drives one serial journey through:

1. registration and the dashboard, then the workspaces landing page;
2. workspace and project creation;
3. Settings preferences, profile update, workspace update and audit history;
4. Ollama provider creation, connection test and model refresh;
5. single-model playground execution;
6. prompt save, new version and restore as a new version;
7. comparison with one live model and one missing model (partial failure isolation);
8. dataset creation, record mutation, JSON import, versioning and a risky record;
9. reference-metric evaluation, 3/3 case results and case detail;
10. observability trace and span tree;
11. security scan, redacted finding detail and finding review;
12. one live AI security test case with a verdict and response detail;
13. analytics figures, report generation and CSV/PDF downloads;
14. sign-out and protected-route redirect back to `/login`, plus a final assertion that no
    browser console or page errors occurred.

Last verified on 2026-11-09 against the Compose stack: **1 journey passed**. Failure
screenshots, video and traces are written to `frontend/test-results/`. The journey is part
of the `browser-e2e` CI job, which starts PostgreSQL, Redis, the Django stack, the worker,
Ollama and Chromium.

### CI

`.github/workflows/ci.yml` runs on push, pull request and manual dispatch:

1. Backend `ruff --select F,I`, mypy on the typed modules, `pip-audit`, Django checks,
   migration drift and pytest.
2. Frontend `npm ci`, ESLint, TypeScript typecheck, production-dependency npm audit,
   Karma/ChromeHeadless and the production build.
3. Full Docker stack + Ollama + Chromium + Playwright acceptance journey, with artifacts
   and service logs on failure.

Any required check failing fails the workflow.

## What the automated suite cannot prove

- PostgreSQL-specific SQL, constraints, indexes and migration behavior. The live stack was
  verified manually on 2026-11-09.
- Real Redis broker/result-backend behavior across arbitrary process failures. A full
  restart and worker stop/start were verified manually; queued-task redelivery was not.
- Real Z.ai behavior beyond adapter unit tests; an operator key is still required. Live
  Ollama execution was verified manually with `llama3.2:1b`.
- Browser E2E in CI. The Playwright journey exists and passed locally against the full
  Docker stack on 2026-11-09, but CI cannot provide PostgreSQL, Redis, a worker, Ollama or
  a browser.
- Provider timeout/recovery/retry/backoff is covered by deterministic transport tests;
  live provider failure recovery still needs a target provider to be unavailable.
- Rate limiting is covered by API tests; distributed behavior behind multiple API
  replicas depends on the shared cache/Redis configuration.
- Dependency audit results change over time; CI runs the audit on every push.

## Manual Docker/PostgreSQL/Redis acceptance

This procedure was executed successfully on 2026-11-09 against Docker Desktop `29.9.2`
with the current working tree; the evidence is in [HANDOVER.md](HANDOVER.md#verification-evidence).
Repeat it on a clean host or after infrastructure changes. The notes below distinguish the
parts exercised in that pass from the parts still requiring a full manual run.

### 1. Build and start

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY, POSTGRES_PASSWORD, PROVIDER_SECRET_KEYS in .env.
docker compose -f infrastructure/docker-compose.yml --env-file .env up --build -d
docker compose -f infrastructure/docker-compose.yml --env-file .env ps
```

Expected: `db` and `redis` healthy; `backend` healthy; `worker` and `beat` running;
`frontend` running. Inspect logs for migration or startup errors:

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env logs backend
docker compose -f infrastructure/docker-compose.yml --env-file .env logs worker
```

### 2. Configuration and migration checks

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env exec backend \
  python manage.py check --settings=config.settings.dev
docker compose -f infrastructure/docker-compose.yml --env-file .env exec backend \
  python manage.py makemigrations --check --dry-run --settings=config.settings.dev
```

Expected: no issues and no migration drift.

### 3. Health and worker round trip

```bash
curl -fsS http://localhost:8000/api/v1/health/
curl -fsS "http://localhost:8000/api/v1/health/worker/?probe=1"
```

Expected: HTTP 200, `"status":"ok"`, database `ok`, broker `ok`, worker echo `ping`.
Stop the worker and repeat the probe; it should report degraded/503, not a false OK.

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env stop worker
curl -sS "http://localhost:8000/api/v1/health/worker/?probe=1"
docker compose -f infrastructure/docker-compose.yml --env-file .env start worker
```

### 4. Browser acceptance journey

**2026-11-09 coverage:** the Playwright journey in
`frontend/e2e/full-acceptance.spec.ts` now clicks through every step below against the
Docker-served UI and live Ollama. Run `npm run e2e` from `frontend/` instead of repeating
these interactions by hand; the list remains the manual procedure for browsers or builds
Playwright cannot drive.

Use a fresh account unless you have a disposable workspace.

1. Open <http://localhost:4200> and register.
2. Create a workspace; verify the creator is owner.
3. Create a project.
4. Add an Ollama provider (or Z.ai with a real key), test the connection and refresh the
   model list.
5. Run a single-model playground prompt; verify content/latency/token fields or a
   structured error.
6. Run a two-model comparison; verify one failure does not erase the other result.
7. Save a prompt; edit it; verify a new version and restore behavior.
8. Create a dataset; add a record; import a small JSON/JSONL/CSV file; verify the version
   increments.
9. Start an evaluation with a reference metric; wait for completion; inspect per-case
   results and aggregates.
10. Start an evaluation with a judge metric if a judge model is available; verify the judge
    and metric results are visible, or a metric error is recorded.
11. Open observability; verify the execution/evaluation trace and span tree.
12. Run a security scan against the dataset/prompt/execution; inspect redacted evidence
    and review a finding.
13. Run an AI security test against configured models; verify pass/fail/inconclusive
    values and that provider errors are inconclusive.
14. Open analytics; verify counts reconcile with stored records; create a report and
    download CSV and PDF.
15. Log out and verify protected routes/API return to the login flow.

Record any browser console errors and backend/worker exceptions. A UI that renders without
a working backend is not acceptance evidence.

### 5. Persistence and restart

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env restart
curl -fsS http://localhost:8000/api/v1/health/
```

**Verified on 2026-11-09:** a full restart of all six services returned API health 200 and
worker echo `ping`; the workspace, project and completed evaluation were still present.
Log in again and verify your own workspaces/executions/evaluations survive. PostgreSQL data
is in the `postgres_data` volume. Redis data is in `redis_data`; Redis is still not the
authoritative result store.

### 6. Provider timeout/recovery

- Point a provider at a non-running local endpoint, or stop Ollama.
- Run a playground prompt. Expected: an execution result with a structured
  provider/network error, not a 500 or a lost execution.
- Restart Ollama and rerun. Expected: success.
- Stop the worker while an evaluation is queued, then restart it. Expected: the queued
  task is processed after recovery if Redis retained it; otherwise mark/rerun the job.
  There is no automatic retry policy for provider failures.

### 7. Backup/restore drill

Follow the manual dump/restore commands in [DATA-MODEL.md](DATA-MODEL.md), but restore
into a **separate** database first. Verify row counts, provider secret decryption with the
matching key, and a login. Do not treat a dump as a verified backup until a restore has
succeeded.

**Verified on 2026-11-09:** a 197,121-byte dump restored into a separate database; the
restored user password check returned `True` with 46 migrations and 39 tables. The restore
database and dump were removed after verification. The scheduled `backup_database`
command/task and retention policy are implemented; see [HANDOVER.md](HANDOVER.md) for the
latest run. Always verify provider-secret decryption separately with the matching
`PROVIDER_SECRET_KEYS`.

### 8. Security regression checks

- Create a second workspace with a second user.
- Verify the first user cannot read the second workspace's project/provider/dataset by
  ID (expect 404).
- Verify a viewer cannot mutate, a member cannot manage providers/members, and an admin
  cannot remove/demote the owner.
- Verify provider API keys never appear in API responses, logs or traces.
- Verify an Ollama endpoint outside the loopback/host-gateway allow-list is rejected.
- Verify a failed login is generic and a reused refresh token is rejected.

## Still required for specification acceptance

The following are not yet automated or fully verified:

| Requirement | Status |
|---|---|
| Automated end-to-end journey | Implemented and wired into the `browser-e2e` CI job; passed locally against the full Docker stack on 2026-11-09. |
| Rate-limit tests/implementation | Implemented; API tests cover login/model-call throttles. |
| Worker restart/retry/reliability test | Manual stop/start and full restart passed; provider transport retries are unit-tested. Queued-task redelivery remains broker-dependent. |
| Provider timeout test | Implemented as deterministic transport tests. |
| Duplicate submission/idempotency | Validation tests exist; no idempotency key. |
| Lint/type check/dependency audit | Required CI gates. |
| Live PostgreSQL/Redis Compose run | **Passed** on 2026-11-09; see [HANDOVER.md](HANDOVER.md#verification-evidence). |
| Backup restore | **Passed** manually on 2026-11-09; scheduled backup command and retention implemented. |
| Live Z.ai verification | Blocked without an operator key. |
| OTLP collector verification | **Passed** against the supplied collector config on 2026-11-09. |

These gaps are tracked with milestone status in [HANDOVER.md](HANDOVER.md).
