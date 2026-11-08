# ModelScope AI — Implementation Plan (Milestone 1)

Date: 2026-11-09 · Baseline: `ModelScope_AI_Coding_Agent_Specification.pdf` v1.0

## 1. Repository audit (Section 16, first task)

- Existing tracked files before this work: `ModelScope_AI_Coding_Agent_Specification.pdf`, `README.md` (placeholder).
- The repository contains **no application code** — it is effectively empty. Per the agent rules, we initialise the agreed structure without destructive changes.
- Framework versions: none installed yet. Chosen pins are recorded in ADR-0002.

## 2. Milestone scope

Per Section 13 / 16, this increment delivers **Milestone 1 — Foundation only**:

- Repo skeleton matching Sections 5 & 6 (backend modular monolith layout, Angular feature-based layout).
- Django + Django REST Framework project with versioned API base path `/api/v1/`.
- PostgreSQL configuration (UUID PKs, UTC timestamps enforced by settings conventions).
- Redis + Celery worker and beat wired up, with a verifiable test task (`common.ping`).
- Docker Compose for frontend, backend, db, redis, worker, beat — health checks, named volumes, `.env.example`.
- Health endpoints: `/api/v1/health/` (DB + Redis/Celery broker connectivity) and `/api/v1/health/worker/` (live round-trip through a Celery task).
- Smoke tests: backend pytest (health, config, encryption helper), frontend build + basic app spec.
- CI workflow running lint/tests/build.
- README with exact setup commands; docs (ADRs, assumptions).

We **stop after Milestone 1** and wait for review before Milestone 2 (Identity/tenancy).

## 3. Environment limitation (documented, not hidden)

Docker is **not available inside this development sandbox**, so `docker compose up` cannot be executed here. Mitigations:

- All services are also runnable locally with SQLite fallback **only for unit tests**; integration paths target PostgreSQL as the source of truth.
- Compose files, Dockerfiles and healthchecks are written to spec and validated statically (YAML parse, referenced context paths exist).
- The verification report states exactly which commands were run natively and which require a Docker host.

## 4. Assumptions & defaults (no owner-blocking decisions found)

1. Python 3.12, Django 5.x LTS line, DRF 3.15+, celery 5.x, psycopg 3.
2. Angular standalone components + Tailwind CSS v3 (stable toolchain), strict TypeScript.
3. Auth tokens (SimpleJWT) are introduced in Milestone 2, not now — Milestone 1 has no auth surface to secure.
4. Provider credential encryption helper (Fernet, key from env) lands in `common/encryption` now because Section 11 requires it early; the key never enters source control.
5. Sentry/OTLP exporter endpoints stay unconfigured by default; OpenTelemetry SDK wiring is Milestone 6 per roadmap, but the config seam is reserved.

## 5. Proposed initial directory structure

```
backend/
  config/settings/{base,dev,prod}.py, urls.py, wsgi.py, asgi.py, celery.py
  apps/{accounts,workspaces,projects,providers,models_registry,prompts,
        playground,datasets,evaluations,observability,security_scans,analytics}/  (created in M2+)
  integrations/providers/  integrations/evaluation/  integrations/telemetry/
  common/{encryption,exceptions,pagination,permissions,audit}/
  tests/  manage.py  requirements/*.txt  Dockerfile
frontend/            # Angular workspace (generated with ng CLI)
infrastructure/docker-compose.yml (+ profiles)
docs/{IMPLEMENTATION_PLAN.md, adr/, provider-guides placeholder}
.env.example  README.md  .gitignore  .github/workflows/ci.yml
```

## 6. Verification plan (acceptance checklist §17)

| Check | Command | Status when done |
|---|---|---|
| Migrations apply cleanly | `python manage.py migrate` | pending |
| DB connectivity via health | `curl /api/v1/health/` or pytest | pending |
| Celery/Redis round trip | `pytest -k worker` with eager mode + live check script | pending |
| Backend smoke tests | `pytest` | pending |
| Frontend builds | `npm run build` | pending |
| No secrets committed | grep scan of git diff | pending |
