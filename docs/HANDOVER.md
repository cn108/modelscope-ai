# Handover and final status

Baseline: specification v1.0 (8 November 2026), repository branch
`feature/milestone-7-security`, 9 November 2026. The final-phase changes, the README
product tour and its screenshots are committed to `main` and pushed to GitHub. No
production deployment was performed.

## Executive status

The product milestones and the hardening scope are implemented. Automated backend,
frontend, lint, type, audit and browser-journey checks pass locally, the Docker stack was
rebuilt with the final code, and PostgreSQL backup/restore and OTLP export were exercised.
**No live Z.ai call is possible without an operator key**, and no production TLS/host
target was supplied. The application is production-ready in code and configuration, but
the final production promotion still needs a real host, TLS, secrets and off-host backup
storage.

| Area | Status | Evidence |
|---|---|---|
| M1 Foundation | **Complete** | Django/Angular/Compose/health/migrations; live stack healthy; report in [milestones/MILESTONE-1.md](milestones/MILESTONE-1.md). |
| M2 Identity and tenancy | **Complete** | Auth, workspaces, four roles, RBAC, audit, cross-tenant tests. |
| M3 Provider layer | **Complete; live Z.ai blocked** | Z.ai/Ollama/LM Studio adapters, encrypted secrets, retries/timeouts/concurrency; report in [milestones/MILESTONE-3.md](milestones/MILESTONE-3.md). |
| M4 Playground | **Complete** | Single/compare runs, failure isolation, history/rerun, versioned prompts, live Ollama execution. |
| M5 Datasets/evaluation | **Complete** | Imports, CRUD, versioned metrics, per-case results, reruns, human reviews. |
| M6 Observability | **Complete** | Database traces, spans, rollups, retention, OTLP export verified against a real collector. |
| M7 Security | **Complete** | Heuristic scans, redacted evidence, review workflow, dashboards. |
| M8 Analytics/reporting | **Complete** | Filters, comparison, exports, explicit cost availability. |
| M9 AI security testing | **Complete** | 18 reviewed cases; live Ollama run 18/18, 0 provider errors, 14 pass/3 fail/1 inconclusive. |
| Specification Hardening | **Complete in code/config** | Rate limits, CSP/headers, backups/retention, CI quality gates, browser E2E, production profile, monitoring examples. |
| Settings | **Complete for implemented capabilities** | General, Profile, Workspace, Team, Providers, Security/export, Audit, About; API Keys/Notifications omitted rather than faked. |
| UI/UX | **Implemented** | ChatGPT-inspired shell; responsive sidebar; consistent cards/tables/forms/empty/error states. |
| Live Z.ai | **Blocked** | Requires an operator API key; adapter tested against a deterministic stub. |
| Production deployment | **Not performed** | No TLS/host target; production Compose is config- and image-validated only. |

## Verification evidence

| Check | Command / context | Result |
|---|---|---|
| Backend tests | `cd backend && pytest -q` | **176 passed** |
| Backend lint | `ruff check --select F,I .` | pass |
| Backend types | `mypy apps/accounts common integrations/evaluation integrations/providers` | pass |
| Backend dependency audit | `pip-audit -r requirements/base.txt` | 0 known vulnerabilities |
| Frontend specs | `npm test -- --watch=false --browsers=ChromeHeadless` | **23 passed** |
| Frontend lint/typecheck | `npm run lint`, `npm run typecheck` | pass |
| Frontend production audit | `npm audit --omit=dev --audit-level=high` | 0 vulnerabilities |
| Frontend build | `npm run build` | pass |
| Docker image rebuild | `docker compose ... build backend frontend worker beat` | pass |
| Live stack | `docker compose ... ps`; health endpoints | six services running/healthy |
| Migrations | `showmigrations` in container | accounts/providers/evaluations latest applied |
| Backup command | `python manage.py backup_database --label final-verification` in container | pass; 244,156-byte dump created |
| Scheduled backup wiring | prod image settings check | `BACKUP_ENABLED=True`, `database-backup` and `observability-maintenance` scheduled |
| Restore drill | `pg_restore` into `modelscope_restore_final` | pass; 20 users, 19 workspaces, 49 migrations; temporary DB/dump removed |
| Workspace export API | live `POST /workspaces/{id}/export/` | 200; expected format, no credential fields |
| OTLP collector | collector + exported span | collector received `provider.generate` with attributes |
| Production Compose | `docker compose -f infrastructure/docker-compose.prod.yml config --quiet` | pass |
| Production static build | prod image `collectstatic --noinput` | 154 files copied; volume owned by `appuser` |
| Browser journey | `npm run e2e` against the Docker stack | **1 passed (25.7s)** after the final backend/frontend rebuild |

### Restore-drill note

The restore used the container's `pg_dump`/`pg_restore` 17 client against the PostgreSQL
16 server. `pg_restore` reported one unsupported `SET transaction_timeout` statement but
restored all schema and data; the temporary database had the expected users, workspaces
and 49 migrations. Production operators should use a PostgreSQL client matching the
server major version to avoid that warning.

### Runtime issues found and fixed during this phase

- The frontend nginx resolved the backend container name once at startup, so recreating
  only the backend left the frontend returning 502 until nginx restarted. The nginx config
  now uses a Docker DNS resolver and a shared upstream zone, and re-resolves the backend.
- Angular's production build injected an inline `onload` handler for critical CSS, which
  the strict CSP blocked. `inlineCritical` is disabled so the CSP remains strict.
- The backend image lacked `pg_dump`; `postgresql-client` was added and the backup command
  now reports a clear error if the client tools are missing.
- The frontend nginx now gzip-compresses JavaScript/CSS/JSON, which keeps large bundles intact
  on slow or bandwidth-limited links (including temporary tunnels) and reduces transfer size.
- The CI Playwright job installed the browser before `npm ci`; the order is now correct.

### What remains unverified

- **Live Z.ai**: no operator API key. The adapter, error handling and model catalogue are
  tested, but a real cloud call, model refresh and evaluation were not run.
- **Live LM Studio**: no LM Studio instance was available. Endpoint rules and adapter
  behavior are covered by tests.
- **Production host/TLS**: the production profile was validated and its images built, but
  it was not deployed to a real domain with TLS, a proxy and managed secrets.
- **Queued-task redelivery under arbitrary broker failure**: restart/health behavior was
  tested; exactly-once delivery is not claimed and Celery does not provide it.
- **GitHub Actions execution**: the workflow is complete, but it cannot be executed from
  this local workspace. CI results should be confirmed on the first push.

## Pull request status

PR #5 was merged on 2026-11-09 after its four CI checks passed. The merge commit is
`1f2a72b396cab5bee22cd369a9f6ca10e6c191df`. The final-phase hardening changes and the
README product tour are committed to `main` and pushed to GitHub. No production
deployment was performed.

## Remaining work

### Blocking only production promotion (operator inputs)

1. Supply a Z.ai API key and run provider test, model refresh, one playground call and one
   evaluation.
2. Provide the production hostname/TLS termination and set `DJANGO_ALLOWED_HOSTS`,
   `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to the real origins.
3. Store `PROVIDER_SECRET_KEYS` and provider credentials in a secret manager; copy the
   `backup_data` volume off-host and test a restore on the target PostgreSQL.
4. Point monitoring at the real origins and route the alert rules to an on-call channel.

### Accepted residual risks (documented, not hidden)

- JWTs remain in browser `localStorage`; CSP and short rotating tokens reduce but do not
  eliminate XSS impact. httpOnly cookies are the stronger design.
- Non-trace records have no time-based retention; deletion is workspace-scoped and
  cascading, with a JSON export for admins. There is no per-data-subject workflow.
- Human review is a multi-reviewer label/disagreement feature, not a full annotation queue.
- Heuristic security scans/tests can produce false positives/negatives.
- Generic OpenAI-compatible and Hugging Face providers remain out of scope (ADR-0005).

## Settings scope

Implemented and backend-backed: General preferences (display name, time zone, date format,
default workspace/landing page), Profile/password/logout, Workspace details/members/
invite/role/remove/delete/export, Providers (configure/test/models/credentials), Security,
Audit and About.

**API Keys** and **Notifications** are intentionally absent: the application has no API-key
issuance or notification-delivery backend. No non-functional controls were added.

## Milestone reports

- [M1](milestones/MILESTONE-1.md)
- [M2](milestones/MILESTONE-2.md)
- [M3](milestones/MILESTONE-3.md)
- [M4](milestones/MILESTONE-4.md)
- [M5](milestones/MILESTONE-5.md)
- [M6](milestones/MILESTONE-6.md)
- [M7](milestones/MILESTONE-7.md)
- [M8](milestones/MILESTONE-8.md)
- [M9 AI security testing](milestones/MILESTONE-9.md)

## Go/no-go

| Question | Answer |
|---|---|
| Is the core product feature set usable? | **Yes**, subject to the documented limitations. |
| Are P0 code/configuration blockers closed? | **Yes** for rate limits, backups, CSP, CI gates, E2E, production profile and Settings. |
| Is it deployed and live-verified in production? | **No**; no production host/TLS or Z.ai key was supplied. |
| Can a new engineer run it? | **Yes** — README, Docker Compose, tests and this handover. |
| Recommended next step | Supply Z.ai and production origin/secrets, then run the target-stack acceptance in [TESTING.md](TESTING.md). |

## Documentation map

- [README](../README.md) — setup and feature overview.
- [ARCHITECTURE](ARCHITECTURE.md) — components and flows.
- [API](API.md) — endpoints and examples.
- [DATA-MODEL](DATA-MODEL.md) — ER diagram, invariants, migrations.
- [PROVIDERS](PROVIDERS.md) — Z.ai/Ollama/LM Studio, endpoint rules, retries.
- [EVALUATION](EVALUATION.md) — metrics, versions, reviews, reproducibility.
- [SECURITY](SECURITY.md) — roles, secrets, privacy/retention, gaps.
- [OPERATIONS](OPERATIONS.md) — configuration, backups, production profile, monitoring.
- [TESTING](TESTING.md) — automated and manual acceptance.
- [TROUBLESHOOTING](TROUBLESHOOTING.md) — common failures.
- [ADRs](adr/) — architecture/version/encryption/scope decisions.
