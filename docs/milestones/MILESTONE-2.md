# Milestone 2 — Identity, tenancy and RBAC

Date: 2026-11-09 · Baseline: specification v1.0 §13 (Milestone 2)
Status: **complete against its exit criterion** (permission and cross-tenant tests pass)

> Final-phase note (9 November 2026): the limitations at the bottom describe the state at
> M2 exit. Later milestones added live PostgreSQL/Redis Compose runs, Karma specs, the
> Playwright journey and CI gates; see [HANDOVER](../HANDOVER.md#verification-evidence).

## Delivered

- Email/password authentication: `register`, `login`, `refresh` (rotation + blacklist) and `me`.
  Argon2 password hashing; short-lived JWT access tokens with rotating refresh tokens.
- Workspace tenant boundary with owner and settings, plus memberships with
  `owner` / `admin` / `member` / `viewer` roles and one membership per user per workspace.
- Projects scoped to a workspace, with creator tracking.
- Server-side role enforcement on every workspace, membership and project operation.
  Cross-tenant access returns 404 (no existence disclosure); insufficient in-tenant role returns 403.
- Audit events for workspace create/update/delete and membership add/role-change/remove.
- Angular: login/register screen, auth guard, bearer-token interceptor and a
  workspace/project/member management page with role-aware controls.
- Migrations for `accounts` (M1 fix), `workspaces`, `projects` and `common` audit events.

## API endpoints

| Endpoint | Methods |
|---|---|
| `/api/v1/auth/register/` | POST |
| `/api/v1/auth/login/` | POST |
| `/api/v1/auth/refresh/` | POST |
| `/api/v1/auth/me/` | GET |
| `/api/v1/workspaces/` | GET, POST |
| `/api/v1/workspaces/{id}/` | GET, PATCH, DELETE |
| `/api/v1/workspaces/{id}/members/` | GET, POST |
| `/api/v1/workspaces/{id}/members/{membership_id}/` | PATCH, DELETE |
| `/api/v1/projects/` | GET (optional `?workspace=`), POST |
| `/api/v1/projects/{id}/` | GET, PATCH, DELETE |

## RBAC matrix

| Action | Viewer | Member | Admin | Owner |
|---|---|---|---|---|
| Read workspace, members, projects | yes | yes | yes | yes |
| Create project | no | yes | yes | yes |
| Update/delete project | no | own projects only | any | any |
| Update workspace | no | no | yes | yes |
| Delete workspace | no | no | no | yes |
| Add/remove members | no | no | member/viewer only | any except owner |
| Change roles | no | no | member/viewer only | admin/member/viewer |
| Grant or revoke admin | no | no | no | yes |

The owner membership is immutable and the owner cannot be removed. Ownership transfer is
intentionally not supported in Milestone 2.

## Decisions and assumptions

- `Workspace.owner` and the owner `Membership` are created atomically; the owner row is
  protected from demotion and deletion in the service layer.
- Cross-tenant object access returns 404; this prevents object-existence probing.
- Audit rows use `SET_NULL` for workspace/actor so membership history survives workspace deletion.
- JWT signing uses the runtime `SECRET_KEY` (SimpleJWT default) so dev/test secret overrides
  are honoured; the previous eager binding produced an empty HMAC key when the fallback applied.
- Access/refresh tokens are persisted in `localStorage`. This is convenient for the SPA but
  exposed to XSS; revisit with httpOnly cookies plus CSRF protection during hardening.

## Verification

| Check | Command | Result |
|---|---|---|
| Django configuration (test) | `python manage.py check --settings=config.settings.test` | no issues |
| Django configuration (dev) | `python manage.py check --settings=config.settings.dev` | no issues (dev-key warning only) |
| Migrations apply | `python manage.py migrate --settings=config.settings.test` | all migrations OK |
| No missing migrations | `python manage.py makemigrations --check --dry-run --settings=config.settings.test` | No changes detected |
| Backend tests | `pytest` | **37 passed** |
| Frontend production build | `npm run build` | success; 284.67 kB initial (80.19 kB transfer) |
| Browser smoke test | manual: login, workspaces, projects and member roles | pass |

New tests cover registration/login/refresh rotation and revocation, unauthenticated access,
workspace creation and owner membership, cross-tenant list/read isolation, member/admin/owner
permission boundaries, owner protection, duplicate-member conflicts, project creator rules,
viewer restrictions, audit records and cascading workspace deletion.

## Not verified / limitations

- No live PostgreSQL, Redis or Docker daemon in the sandbox, so the Compose stack and the live
  Celery round trip were not executed. Database and HTTP behaviour was verified with SQLite and
  the Django test client only.
- The frontend was build-verified and manually smoke-tested for login and workspace rendering;
  there is no automated Chrome/Karma or end-to-end suite yet.
- `.env.example` is now provided. The CI workflow and full README remain outstanding from Milestone 1.
- The client does not automatically refresh an expired access token; a 401 ends the session.
- Member/project lists are not paginated in the UI (the API is paginated).

## Next milestone

Milestone 3 (provider layer: encrypted credentials, adapters, connection tests) was completed
in the following milestone; see [MILESTONE-3](MILESTONE-3.md).
