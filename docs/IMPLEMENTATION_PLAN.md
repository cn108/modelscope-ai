# ModelScope AI — Implementation Plan (Milestones 1–2)

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

Work should stop for review before Milestone 3 (provider layer). Milestone 3 has not been started.

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
5. Sentry/OTLP exporter endpoints stay unconfigured by default; OpenTelemetry wiring remains Milestone 6.

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
| Celery/Redis round trip | `pytest tests/test_health.py` (eager mode) | partial — live Redis/worker not exercised |
| Backend tests | `pytest` | pass — 37 passed |
| Frontend builds | `npm run build` | pass |
| No secrets committed | `git ls-files` + secret grep scan | pass — no `.env` tracked |
| README and `.env.example` | file existence | partial — `.env.example` added; full README outstanding |
| CI workflow | `.github/workflows/` | **outstanding** |

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

Status: **not started** (encrypted provider credentials, adapters, connection tests).
