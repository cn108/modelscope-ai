# ModelScope AI — Implementation Plan (Milestones 1–6)

Date: 2026-11-09 · Baseline: `ModelScope_AI_Coding_Agent_Specification.pdf` v1.0

## 1. Repository audit (Section 16, first task)

- Existing tracked files before this work: `ModelScope_AI_Coding_Agent_Specification.pdf`, `README.md` (placeholder).
- The repository contained **no application code** — it was effectively empty. Per the agent rules, we initialised the agreed structure without destructive changes.
- Framework versions: none installed initially. Chosen pins are recorded in ADR-0002.

## 2. Milestone scope

Milestone 1 delivered the foundation: repo skeleton matching Sections 5 & 6, Django + DRF with
`/api/v1/`, PostgreSQL configuration, Redis/Celery wiring, health endpoints, encryption helper,
Angular shell, Docker Compose, tests and ADRs.

Milestone 2 delivered identity and tenancy: registration/login/refresh/me, workspaces,
memberships with four roles, projects, server-side RBAC, cross-tenant isolation, audit events and
the corresponding Angular screens. See [Milestone 2 report](milestones/MILESTONE-2.md).

Milestone 3 delivered the provider layer (encrypted credentials, Z.ai and local
Ollama adapters, connection tests) and the shared design system. Milestone 4
added the playground, execution history and versioned prompts; see
[MILESTONE-4.md](milestones/MILESTONE-4.md). Milestone 5 added datasets with
validated imports and record management, the metric registry (built-in scorers
plus DeepEval judge metrics), and Celery-backed evaluations with immutable
per-case results and repeatable reruns; see
[MILESTONE-5.md](milestones/MILESTONE-5.md). Milestone 6 added execution
traces and spans on the existing playground and evaluation paths, latency and
token metrics, explicit cost estimates, a filterable observability dashboard
and a trace explorer; see [MILESTONE-6.md](milestones/MILESTONE-6.md).

## 3. Environment limitation (documented, not hidden)

The Docker CLI is present, but the daemon is **not reachable from this development sandbox**
(`permission denied` on the Docker socket), so `docker compose up` cannot be executed here. Mitigations:

- SQLite is used **only** for hermetic unit/API tests; integration paths still target PostgreSQL as the source of truth.
- Compose files, Dockerfiles and healthchecks are written to spec and validated statically; a full
  Compose start is still required on a Docker host.
- Verification reports state exactly which commands ran natively and which require a Docker host.

## 4. Assumptions & defaults

1. Python 3.12, Django 5.x LTS line, DRF 3.15+, celery 5.x, psycopg 3.
2. Angular standalone components + Tailwind CSS v3, strict TypeScript.
3. SimpleJWT is used for authentication; JWT signing follows the runtime `SECRET_KEY`.
4. Provider credential encryption helper (Fernet, key from env) lands in `common/encryption` early;
   the key never enters source control.
5. Sentry/OTLP exporter endpoints stay unconfigured by default. OpenTelemetry wiring is present as of Milestone 6: database traces always record, and OTLP/HTTP export is opt-in through `OTEL_EXPORTER_OTLP_ENDPOINT`.

## 5. Initial directory structure

```
backend/
  config/settings/{base,dev,prod,test}.py, urls.py, wsgi.py, asgi.py, celery.py
  apps/{accounts,workspaces,projects}/          # implemented in M1–M2
  apps/{providers,models_registry,prompts,playground,datasets,evaluations,
        observability,security_scans,analytics}/  # M3+
  integrations/providers/  integrations/evaluation/  integrations/telemetry/
  common/{encryption,exceptions,pagination,permissions,audit}/
  tests/  manage.py  requirements/*.txt  Dockerfile
frontend/
  src/app/{core,shared,features}/
infrastructure/docker-compose.yml
docs/{IMPLEMENTATION_PLAN.md, milestones/, adr/}
```

## 6. Verification status (acceptance checklist §17)

| Check | Command | Status |
|---|---|---|
| Migrations apply cleanly | `python manage.py migrate --settings=config.settings.test` | pass on SQLite test DB; live PostgreSQL unverified |
| DB connectivity via health | `pytest tests/test_health.py` | pass |
| Celery/Redis round trip | `pytest tests/test_health.py` (eager mode); M5/M6 live checks used a real worker over the filesystem broker | partial — real worker exercised; live Redis/PostgreSQL pending a host |
| Backend tests | `pytest` | pass — 120 passed |
| Frontend builds | `npx ng build` | pass |
| Frontend specs | `npx ng test --watch=false --browsers=ChromeHeadless` | pass — 21 specs |
| No secrets committed | `git ls-files` + secret grep scan | pass — no `.env` tracked |
| README and `.env.example` | file existence | partial — `.env.example` added; full README outstanding |
| CI workflow | `.github/workflows/ci.yml` | present — Django and Angular jobs, green on `main` |

## 7. Milestone status

### Milestone 1 — Foundation

Status: **code complete; handover partial.** Backend boots, migrations apply, smoke tests pass and
the Angular production build succeeds. The live Compose stack, CI workflow and full README remain outstanding.

### Milestone 2 — Identity/tenancy

Status: **complete against its exit criterion** — permission and cross-tenant tests pass.

- Auth, workspaces, memberships, projects and RBAC are implemented with migrations.
- 37 backend tests pass, including cross-tenant IDOR, role boundaries and audit assertions.
- Angular login/register, guard, interceptor and workspace management UI build successfully and
  passed a manual browser smoke test for login, workspaces and role rendering.
- Full report: [MILESTONE-2.md](milestones/MILESTONE-2.md).

### Milestone 3 — Provider layer

Status: **code complete and merged** — encrypted provider credentials, Z.ai and
Ollama adapters, connection/model endpoints and the redesigned UI. Live Z.ai
verification still requires a user-supplied API key.

### Milestone 4 — Playground

Status: **complete against its exit criteria** — single and two-model runs,
per-model metrics and failure isolation, execution history with rerun, saved
prompts with append-only versions and restore, and immutable execution
snapshots. Full report: [MILESTONE-4.md](milestones/MILESTONE-4.md).

### Milestone 5 — Datasets and evaluation

Status: **complete against its exit criteria** — dataset CRUD with validated
JSON/JSONL/CSV imports and record management, a metric registry (three built-in
reference metrics plus DeepEval answer relevancy, faithfulness and contextual
relevancy), Celery-backed runs with queued/running/completed/failed status,
per-case result persistence, aggregate summaries, model comparison and
repeatable reruns against frozen snapshots. Full report:
[MILESTONE-5.md](milestones/MILESTONE-5.md).

### Milestone 6 — Observability

Status: **complete against its exit criteria** — execution traces and span
trees are written from real Playground, Evaluation and judge calls; the
dashboard aggregates latency, tokens, failures, model/provider usage and
explicitly configured estimated costs; the trace explorer resolves the linked
execution or evaluation and displays its spans, request, response and errors.
The live check ran 4 real calls through a Celery worker and read the records
back from both the API and the Angular UI. Completed days are also aggregated
into daily rollups by a scheduled maintenance task, and raw trace retention is
configurable; the dashboard reads rollups for old days and raw traces for the
live edge. Full report: [MILESTONE-6.md](milestones/MILESTONE-6.md).
