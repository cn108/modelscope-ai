# Milestone 1 — Foundation

Date: 2026-11-09 · Status: **complete against its exit criteria**

## Delivered

- Django 5.2 / Django REST Framework 3.18 modular-monolith backend with PostgreSQL as
  the source of truth and Redis/Celery for asynchronous work.
- Angular 20 standalone SPA, TypeScript, Tailwind, nginx static serving.
- Dockerfiles for backend and frontend, a development Compose stack, health checks,
  environment-driven configuration, and a separate production Compose profile.
- Health endpoints for API/database and broker/worker, with a live Celery round trip
  available through `?probe=1`.
- Fernet provider-secret encryption boundary, JWT authentication, workspace tenancy,
  audit events, and migration-managed schema.
- Initial test suites, migration-drift checks, and documentation for setup,
  architecture, operations, and testing.

## Verification

| Check | Evidence |
|---|---|
| Compose stack | six services running; API, frontend and database healthy on 2026-11-09 |
| Migrations | all migrations applied; `makemigrations --check` reports no drift |
| Health | `/api/v1/health/` returns database `ok`; worker probe returns `ping` |
| Restart | full Compose restart retains workspaces, projects and completed runs |
| Tests | backend and frontend suites pass; production build succeeds |
| Production profile | `docker-compose.prod.yml` validates with `docker compose config` |

## Limitations

- The development stack is HTTP-only; TLS terminates in front of the production profile.
- The production profile was configuration-validated and image-built locally, but no
  production host or TLS certificate was supplied for a live deployment.
- Browser tokens remain in `localStorage`; see [SECURITY](../SECURITY.md) for the
  accepted risk and compensating controls.
