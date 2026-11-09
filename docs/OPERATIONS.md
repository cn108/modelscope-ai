# Operations guide

This guide covers configuration, startup order, health, migrations, backups, retention and
the production checklist. `infrastructure/docker-compose.yml` is the development stack;
`infrastructure/docker-compose.prod.yml` is the production-oriented profile documented
below. Neither file provisions TLS or a managed PostgreSQL/Redis service.

## Configuration sources

- Django loads `/workspace/.env` from the repository root in `config/settings/base.py`.
- Compose reads `.env` through `env_file` and overrides container hostnames.
- `.env` is ignored by git. Never commit it.
- Secrets belong in a secret manager or the platform's environment configuration, not in
  the repository.

Settings modules:

| Module | Use |
|---|---|
| `config.settings.dev` | Local/Compose development. Debug defaults on, insecure fallback key if no key is set. |
| `config.settings.test` | pytest: SQLite in memory, eager Celery, local-memory cache, no provider keys. |
| `config.settings.prod` | Production: fails fast without `DJANGO_SECRET_KEY`, enables SSL redirect/HSTS/secure cookies. |
| `config.settings.preview` | Local preview harness used by the repository's preview server, not a production environment. |

## Startup order

1. PostgreSQL is accepting connections.
2. Redis is accepting connections.
3. Apply migrations once (the Compose backend does this on startup).
4. Start the API.
5. Start the Celery worker.
6. Start Celery beat if rollups/retention are enabled.
7. Start/reload the frontend static server.

The Compose `backend` waits for healthy `db` and `redis`, runs `migrate`, then starts
Gunicorn. `worker` waits for Redis/DB and the backend being started. `beat` waits for
Redis/DB.

In a multi-replica production deployment, run migrations as a separate one-shot job
before rolling API/worker replicas rather than letting every replica race.

## Health checks

```bash
curl -fsS http://localhost:8000/api/v1/health/
curl -fsS "http://localhost:8000/api/v1/health/worker/?probe=1"
```

- `/health/` checks database connectivity; returns `200` when the database is reachable,
  `503` otherwise.
- `/health/worker/` checks the Redis broker; returns `503` when it cannot ping Redis.
- `?probe=1` enqueues `common.debug_echo` and waits briefly for a worker result. A missing
  worker produces a degraded response rather than a false OK.

Health endpoints are unauthenticated by design. Do not expose sensitive dependency
details publicly; the detail strings are intentionally short but can include connection
errors.

## Database migrations

```bash
cd backend
python manage.py migrate
```

Check drift in CI or before a release:

```bash
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

Back up PostgreSQL before applying migrations to important data. See
[DATA-MODEL.md](DATA-MODEL.md) for entity/invariant notes and a manual dump/restore
example.

## Celery worker and beat

Worker:

```bash
cd backend
celery -A config worker --loglevel=INFO
```

Beat (only needed for the daily observability maintenance task):

```bash
cd backend
celery -A config beat --loglevel=INFO
```

The worker executes evaluation, security scan, AI security test and observability tasks.
A queue/broker failure is recorded on the affected run as a failed status with a
`queue_unavailable` error where the service supports it. Re-run the job after restoring
Redis/worker capacity.

Celery configuration uses late acknowledgements, prefetch multiplier 1 and started-task
tracking. This reduces duplicate/lost work but does not make tasks exactly-once. Clients
should avoid submitting duplicate jobs and should inspect existing runs after a worker
restart. Provider transport retries transient network errors, HTTP 429 and HTTP 5xx
responses with exponential backoff, bounded by `PROVIDER_MAX_RETRIES`; non-retryable
auth/validation failures surface immediately. A timeout is stored as a result error.

## Observability maintenance and retention

Daily task: `apps.observability.maintain` at 01:15 UTC when
`OBSERVABILITY_ROLLUP_ENABLED=true`. It:

1. rolls completed days into `TraceRollup` rows per project;
2. if `OBSERVABILITY_TRACE_RETENTION_DAYS` is positive, deletes raw traces older than the
   cutoff after a successful rollup.

Manual run:

```bash
cd backend
python manage.py purge_traces
```

Override the window for one run with `--days N`. `0` disables deletion. A failed rollup
skips deletion for that project so the only copy of the history is not lost. Rollups are
retained even after raw traces are deleted.

**Important:** configured retention applies to raw traces only. Playground executions,
evaluation results, datasets, security findings, AI security test results and reports
remain until deleted with their project/workspace. Workspace admins can download a JSON
snapshot from Settings → Security, or delete the workspace (which cascades to its
projects and records). There is no time-based retention job for those records.

## Backups

`backup_database` creates a custom-format `pg_dump` in `BACKUP_DIR` and applies
`BACKUP_RETENTION_DAYS` to older backups. With `BACKUP_ENABLED=true`, Celery Beat
schedules it daily at 02:30 UTC. The production profile mounts a named `backup_data`
volume into the backend, worker and beat containers; copy it to off-host storage.

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  exec backend python manage.py backup_database --label manual
```

The command requires `pg_dump`/`pg_restore`. The backend image installs
`postgresql-client`; if an older image lacks it, rebuild it or run the command on a host
with the PostgreSQL client tools.

Restore into an empty database:

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  < modelscope-YYYYMMDDTHHMMSSZ.dump
```

Also back up/retain separately:

- the matching `PROVIDER_SECRET_KEYS` (without it, provider secrets cannot be decrypted);
- the deployment `.env`/secret-manager entries;
- the application commit/image tag and lockfiles;
- any external provider configuration/credentials needed to recreate access.

Test a restore into a separate database before relying on the backup. A dump that has
never been restored is not a verified backup.

A manual drill on 2026-11-09 dumped the acceptance database, restored it into a separate
database, verified the restored user password check and the row/schema counts, then removed
the temporary copy. Scheduled backup scheduling and retention are implemented; see the current verification
in [HANDOVER.md](HANDOVER.md).

## Logging and monitoring

- Django logs to stdout with `LEVEL`, timestamp, logger name, trace ID and message.
- Container logs are available through `docker compose logs`.
- There is no bundled log aggregation or metrics backend, but
  `infrastructure/monitoring/` contains a Prometheus/blackbox example, alert rules and an
  OTLP collector configuration.
- OTLP export is optional; without `OTEL_EXPORTER_OTLP_ENDPOINT`, spans stay in-process
  and database traces remain available.
- Monitor `/health/`, `/health/worker/?probe=1`, Celery queue depth, worker availability,
  PostgreSQL disk/connections and Redis memory/eviction.
- Do not log request bodies, provider keys or credentials. Provider errors are sanitized
  in user-facing responses, but operators should still treat logs as sensitive.

## Upgrades and rollback

1. Read the release/migration notes and back up PostgreSQL.
2. Build/pull the new API/worker/frontend images.
3. Apply migrations with a one-shot job.
4. Roll out API then workers (or all together if the migration is backward compatible).
5. Run health checks and a small playground/evaluation smoke test.
6. Keep the previous image tag and database backup until acceptance.

Rollback after a destructive migration may require restoring the database backup, not
just redeploying the old image. There is no automated down-migration framework beyond
Django's migration history.

## Production Compose profile

```bash
docker compose -f infrastructure/docker-compose.prod.yml --env-file .env up --build -d
```

The profile runs `config.settings.prod`, keeps PostgreSQL/Redis on an internal network,
collects static files into a shared volume, runs Gunicorn, schedules backups, and exposes
only the frontend on `APP_PORT` (default 8080). It is still the operator's responsibility
to put TLS, a trusted proxy, off-host backups, log collection and a managed database in
front of it.

## Monitoring and alerting

`infrastructure/monitoring/` contains:

- `otel-collector-config.yaml` — OTLP/gRPC and OTLP/HTTP collector with a debug exporter;
- `prometheus.yml` — blackbox probes for API liveness, worker health and the frontend;
- `alerts.yml` — availability alerts for API, worker, frontend and missing probes;
- `blackbox.yml` — HTTP probe module.

The health probes verify reachability, not business correctness. Add queue-depth,
latency, error-rate and disk/backup-age metrics for a complete production monitoring
plan. OTLP export was verified against the supplied collector configuration; see
[HANDOVER.md](HANDOVER.md).

## Production checklist

- [x] Production settings module and profile supplied.
- [x] Strong `DJANGO_SECRET_KEY`, secure cookies, HSTS and SSL redirect enforced by settings.
- [x] CSP and security headers applied by middleware and nginx.
- [x] Login/model-call/evaluation creation rate limits configured.
- [x] PostgreSQL/Redis kept on an internal Compose network.
- [x] Static files collected into the shared volume.
- [x] Scheduled PostgreSQL backup with retention.
- [x] Workspace export and workspace deletion workflows.
- [x] Prometheus/blackbox/alerting examples and OTLP collector configuration.
- [ ] Put TLS and a trusted reverse proxy in front of the frontend.
- [ ] Set `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to the real origins.
- [ ] Store `PROVIDER_SECRET_KEYS` and provider credentials in a secret manager.
- [ ] Copy backups off-host and test restore on the target PostgreSQL version.
- [ ] Protect `/admin/` with network policy and strong authentication.
- [ ] Configure log aggregation, queue/disk monitoring and on-call routing.
- [ ] Run the full acceptance procedure in [TESTING.md](TESTING.md) on the target stack.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for startup, provider, Celery, Angular and
test failures.
