# Data model and migrations

PostgreSQL is the authoritative store. Domain tables use UUID primary keys, timezone-aware
timestamps and foreign keys that generally cascade within a project/workspace. Redis is a
broker/cache and is never the only store for a user-visible result.

## Entity relationship diagram

The diagram is intentionally high level: it shows ownership and the main relationships,
not every column. Field-level definitions live in the Django models and migrations.

```mermaid
erDiagram
    USER ||--o{ WORKSPACE : owns
    USER ||--o{ MEMBERSHIP : joins
    WORKSPACE ||--o{ MEMBERSHIP : contains
    WORKSPACE ||--o{ PROJECT : contains
    USER ||--o{ PROJECT : creates
    PROJECT ||--o{ PROVIDER_CONFIG : configures
    PROVIDER_CONFIG ||--o| PROVIDER_SECRET : protects
    PROVIDER_CONFIG ||--o{ MODEL_CONFIG : lists
    PROJECT ||--o{ PROMPT : contains
    PROMPT ||--o{ PROMPT_VERSION : versions
    PROJECT ||--o{ EXECUTION : runs
    PROMPT o|--o{ EXECUTION : snapshots
    EXECUTION ||--o{ EXECUTION_RESULT : produces
    PROVIDER_CONFIG ||--o{ EXECUTION_RESULT : serves
    PROJECT ||--o{ DATASET : contains
    DATASET ||--o{ DATASET_RECORD : contains
    PROJECT ||--o{ EVALUATION : runs
    DATASET o|--o{ EVALUATION : snapshots
    EVALUATION ||--o{ EVALUATION_MODEL : selects
    PROVIDER_CONFIG o|--o{ EVALUATION_MODEL : serves
    EVALUATION ||--o{ EVALUATION_RESULT : produces
    EVALUATION_MODEL ||--o{ EVALUATION_RESULT : produces
    PROJECT ||--o{ TRACE : records
    EXECUTION_RESULT o|--o{ TRACE : links
    EVALUATION_RESULT o|--o{ TRACE : links
    TRACE ||--o{ SPAN : contains
    SPAN o|--o{ SPAN : parents
    PROJECT ||--o{ TRACE_ROLLUP : aggregates
    PROJECT ||--o{ TRACE_ROLLUP_STATE : tracks
    PROJECT ||--o{ SECURITY_SCAN : scans
    SECURITY_SCAN ||--o{ SECURITY_FINDING : finds
    SECURITY_FINDING ||--o{ SECURITY_FINDING_EVENT : reviews
    PROJECT ||--o{ SECURITY_TEST_RUN : tests
    SECURITY_TEST_RUN ||--o{ SECURITY_TEST_MODEL : selects
    SECURITY_TEST_MODEL ||--o{ SECURITY_TEST_RESULT : produces
    PROJECT ||--o{ ANALYTICS_REPORT : snapshots
    WORKSPACE ||--o{ AUDIT_EVENT : audits
    USER ||--o{ AUDIT_EVENT : acts

    USER {
        uuid id PK
        string email UK
        string display_name
        bool is_active
        datetime created_at
    }
    WORKSPACE {
        uuid id PK
        uuid owner_id FK
        string name
        json settings
    }
    MEMBERSHIP {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        string role
    }
    PROJECT {
        uuid id PK
        uuid workspace_id FK
        uuid created_by_id FK
        string name
    }
    PROVIDER_CONFIG {
        uuid id PK
        uuid project_id FK
        string kind
        string endpoint
        json settings
        string connection_status
    }
    PROVIDER_SECRET {
        uuid id PK
        uuid provider_id FK
        bytes encrypted_value
    }
    MODEL_CONFIG {
        uuid id PK
        uuid provider_id FK
        string model_id
    }
    PROMPT {
        uuid id PK
        uuid project_id FK
        string name
    }
    PROMPT_VERSION {
        uuid id PK
        uuid prompt_id FK
        int version_number
        text system_prompt
        text user_prompt
    }
    EXECUTION {
        uuid id PK
        uuid project_id FK
        uuid prompt_id FK
        string mode
        string status
        text system_prompt
        text user_prompt
    }
    EXECUTION_RESULT {
        uuid id PK
        uuid execution_id FK
        uuid provider_id FK
        string model_id
        text content
        string status
    }
    DATASET {
        uuid id PK
        uuid project_id FK
        string name
        int version
    }
    DATASET_RECORD {
        uuid id PK
        uuid dataset_id FK
        int position
        text input
        text expected_output
        json context
    }
    EVALUATION {
        uuid id PK
        uuid project_id FK
        uuid dataset_id FK
        int dataset_version
        string status
        json metrics
        uuid judge_provider_id FK
    }
    EVALUATION_MODEL {
        uuid id PK
        uuid evaluation_id FK
        uuid provider_id FK
        string model_id
        string status
    }
    EVALUATION_RESULT {
        uuid id PK
        uuid evaluation_id FK
        uuid model_id FK
        int record_position
        text input
        text generated_response
        json scores
    }
    TRACE {
        uuid id PK
        uuid project_id FK
        uuid execution_result_id FK
        uuid evaluation_result_id FK
        string source
        string role
        string status
        text request_text
        text response_text
    }
    SPAN {
        uuid id PK
        uuid trace_id FK
        uuid parent_id FK
        string name
        string status
        int duration_ms
    }
    TRACE_ROLLUP {
        uuid id PK
        uuid project_id FK
        date day
        string model_id
        int calls
    }
    SECURITY_SCAN {
        uuid id PK
        uuid project_id FK
        string target_type
        uuid dataset_id FK
        uuid prompt_id FK
        uuid execution_id FK
        string status
    }
    SECURITY_FINDING {
        uuid id PK
        uuid scan_id FK
        uuid project_id FK
        string check_key
        string severity
        string status
        text evidence
    }
    SECURITY_FINDING_EVENT {
        uuid id PK
        uuid finding_id FK
        uuid actor_id FK
        string to_status
    }
    SECURITY_TEST_RUN {
        uuid id PK
        uuid project_id FK
        string status
        json case_keys
    }
    SECURITY_TEST_MODEL {
        uuid id PK
        uuid run_id FK
        uuid provider_id FK
        string model_id
    }
    SECURITY_TEST_RESULT {
        uuid id PK
        uuid run_id FK
        uuid model_id FK
        string case_key
        string verdict
    }
    ANALYTICS_REPORT {
        uuid id PK
        uuid project_id FK
        string title
        json snapshot
    }
    AUDIT_EVENT {
        uuid id PK
        uuid workspace_id FK
        uuid actor_id FK
        string action
        json metadata
    }
```

## Ownership and invariants

- **Tenant boundary:** workspace membership is the authorization source. Every project
  resource is reachable only through a project whose workspace has a membership for the
  caller. Cross-tenant access returns `404`.
- **Provider secrets:** `ProviderSecret` is a one-to-one row separate from configuration
  JSON. The value is Fernet-encrypted and never serialized to API responses or traces.
- **Provider scope:** provider configs belong to a project, not a workspace. Reusing a
  provider across projects requires creating a new config.
- **Prompt history:** versions are append-only. Updating a prompt creates a new version;
  restoring creates another version rather than rewriting an old row.
- **Execution snapshots:** an execution stores the system/user prompt and parameters it
  used. Re-running an execution creates a new row and keeps the old one immutable.
- **Dataset versions:** creating, editing, deleting or importing records increments
  `Dataset.version`. Evaluation rows record the dataset name/version and copy each
  record's input, expected output and context into `EvaluationResult`.
- **Evaluation immutability:** completed per-case results are not rewritten by a rerun.
  A rerun creates a new `Evaluation`.
- **Trace links:** a trace can point to an execution result or an evaluation result.
  Playground/evaluation request text is resolved from those linked records; judge calls
  also store their own prompt/response up to 4,000 characters.
- **Rollups:** `TraceRollup` is a pre-aggregated daily history used by analytics. The
  `TraceRollupState` row tracks how far each project has been rolled up. Deleting raw
  traces does not delete rollups.
- **Security evidence:** finding evidence is redacted before storage. The original
  sensitive value is not written into `SecurityFinding`.
- **Reports:** `AnalyticsReport.snapshot` is a frozen report document. Reports are not
  recalculated when source data changes.

## Migrations

Migrations are ordinary Django migrations under:

```text
backend/common/migrations/
backend/apps/*/migrations/
```

Apply them with:

```bash
cd backend
python manage.py migrate
```

Check for model/migration drift (the same check CI runs):

```bash
cd backend
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

The test settings use SQLite for hermetic unit/API tests. That verifies migration
execution and model consistency, but it does **not** prove behavior on PostgreSQL. Run
migrations against PostgreSQL in the Compose stack before accepting a release:

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d db
docker compose -f infrastructure/docker-compose.yml --env-file .env exec backend \
  python manage.py migrate --settings=config.settings.dev
```

### Migration notes

- Back up PostgreSQL before applying migrations to a database with data you care about.
- The API container runs `manage.py migrate` on startup in the supplied Compose file.
  In a multi-replica deployment, run migrations as a single explicit job before rolling
  out API/worker replicas instead of letting every replica race.
- `ProviderSecret.encrypted_value` requires the same `PROVIDER_SECRET_KEYS` used when it
  was written. Restoring a database without that key leaves secrets undecryptable.
- Dataset version numbers are data, not schema. Do not reset them during a restore.
- Trace retention is a data operation, not a migration. Run
  `python manage.py purge_traces` or let the scheduled maintenance task apply it.
- Do not edit applied migration files. Add a new migration for every model change.

## Backup and restore

The repository does not yet contain an automated backup job. The minimum manual procedure
is:

```bash
# Back up PostgreSQL from the running Compose database. The shell inside the
# container reads its own POSTGRES_USER/POSTGRES_DB values.
docker compose -f infrastructure/docker-compose.yml --env-file .env exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > modelscope.dump

# Restore into an empty database.
docker compose -f infrastructure/docker-compose.yml --env-file .env exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < modelscope.dump
```

Also retain:

- the matching `PROVIDER_SECRET_KEYS` in a secret manager, separate from the database
  backup;
- the deployment `.env`/configuration (not in source control);
- any external provider credentials needed to recreate Z.ai access.

Redis persistence is enabled in Compose (`appendonly yes`), but Redis is not a substitute
for a PostgreSQL backup. Queued Celery jobs can be lost if Redis is lost; re-run the
affected evaluations/scans/tests after recovery.

See [OPERATIONS.md](OPERATIONS.md) for the production backup/restore checklist and
[SECURITY.md](SECURITY.md) for retention and secret-handling rules.
