# Milestone 6 — Observability

Date: 2026-11-09 · Status: **complete against its exit criteria** (a real
playground run and a real Celery-backed evaluation generated database traces
with spans; the dashboard and trace explorer read them back through the API and
Angular UI)

## Delivered

- **Execution traces** — one `Trace` row per actual model call, written from the
  existing Playground and Evaluation execution paths. Each row records the
  project, source, call role, provider identity, model, execution status, start
  and end timestamps, total duration, provider latency, token counts, error,
  OpenTelemetry trace id and cost state.
- **Spans** — ordered rows inside a trace with a parent/child tree, operation
  kind, status, timing, attributes and error. The Playground records provider
  preparation and the provider request. Evaluations record preparation, the
  provider request, metric evaluation and one child span per metric.
- **Trace linking** — a trace is constrained to link exactly one
  `ExecutionResult` (Playground) or one `EvaluationResult` (Evaluation). The
  explorer resolves prompt and response text from those rows at read time
  instead of copying them into a second store. Only judge prompts/responses,
  which no other table stores, are retained on the trace (truncated to 4,000
  characters).
- **Judge visibility** — each DeepEval judge call is recorded as a separate
  trace with role `judge`, linked to the case result that triggered it. Provider
  failures that happen before a case receives a result are also recorded as
  failed case traces.
- **Dashboard** — total calls, succeeded/failed counts, failure rate, average
  provider latency (with full-duration fallback), token totals and reporting
  calls, estimated costs, cost availability, an execution trend by day, model
  and provider breakdowns, error categories, slowest calls and recent traces.
- **Filters** — date range (`from`, `to`), provider, model, execution status,
  source (`playground`/`evaluation`) and call role. Filters apply consistently
  to totals, trends, breakdowns, errors, slowest calls and the trace list.
- **Trace explorer** — `/observability` lists traces with request previews and
  links; `/observability/traces/:id` shows the request, response, metadata,
  timing, tokens, cost state, errors and the ordered span tree.
- **OpenTelemetry** — an optional `TracerProvider` wraps the provider call and
  metric evaluation in real OTel spans. When `OTEL_EXPORTER_OTLP_ENDPOINT` is
  set the spans are exported over OTLP/HTTP; otherwise they remain in-process.
  The captured OTel trace id is stored on the database trace. OTel failures
  never break a model call.
- **Logging** — a trace-id context and logging filter attach `trace=<uuid>` to
  application log records without changing existing log formats. A
  configuration error or exporter failure is reported in the dashboard's
  telemetry status rather than crashing boot.
- **Cost monitoring** — explicit, configuration-driven cost estimates by
  provider/model and day. Costs are marked `estimated`, `partial` or
  `unavailable` with a human-readable reason; no vendor price is hard-coded.
- **Workspace isolation** — every endpoint resolves the project membership,
  traces are queried by project, and trace detail requires workspace
  membership. Cross-workspace trace ids return 404.
- **Retention and rollups** — completed days are aggregated into compact
  daily buckets; the dashboard reads those for old days and raw traces for the
  live edge. Raw trace retention is configurable and only deletes days that
  were successfully rolled up. A watermark prevents double counting.

## Existing infrastructure and what was added

Before M6 the repository had no execution tracing, span model, metrics
aggregation, cost estimation or observability screens. The provider layer
already returned token usage, the Playground already stored per-result latency
and tokens, and M5 already stored per-case latency/tokens and metric outcomes.
M6 reuses those records rather than re-running or duplicating executions:

| Existing | M6 use |
|---|---|
| Playground `Execution` / `ExecutionResult` | Source of request, response, latency and tokens; trace links to the result and updates its `estimated_cost` when an estimate exists |
| Evaluation `EvaluationResult` | Source of frozen case input, expected output, response, latency and tokens; trace links to the case |
| `ProviderConfig` and adapters | Provider identity and the single model-call path; no second execution path |
| Celery evaluation task | The task that generates evaluation traces; no event pipeline |
| DeepEval judge adapter | `on_call` hook records judge traces at the point of the real judge call |

No isolated monitoring event stream or synthetic execution records were added.

## Data model

`Trace` (table `observability_trace`):

| Field group | Fields |
|---|---|
| Identity | `id`, `project`, `source`, `role` |
| Link | `execution_result` xor `evaluation_result` (database check constraint) |
| Provider | `provider` (nullable), `provider_name`, `provider_kind`, `model_id` |
| Timing | `started_at`, `ended_at`, `duration_ms`, `provider_latency_ms` |
| Usage | `input_tokens`, `output_tokens` |
| Cost | `estimated_cost`, `cost_currency`, `cost_status`, `cost_detail` |
| Diagnostics | `status`, `error`, `attributes`, `otel_trace_id` |
| Retained text | `request_text`, `response_text` (judge calls only) |
| Audit | `created_at` |

`Span` (table `observability_span`) stores `trace`, optional `parent`,
deterministic `sequence`, `name`, `kind` (`internal`, `client`, `task`),
`status`, `started_at`, `ended_at`, `duration_ms`, `attributes` and `error`.
`(trace, sequence)` is unique.

`TraceRollup` (table `observability_trace_rollup`) stores one daily bucket per
project, source, role, status, provider identity, model and cost currency. It
holds call/success/failure counts, token totals and reporting-call count,
latency and duration sums with sample counts, estimated/unavailable cost
counts, error-category counts and first/last timestamps. `TraceRollupState`
stores the last fully aggregated day per project.

Indexes cover project/start time, project/status, provider/model and
source/role on traces, and project/day plus model and provider access paths on
rollups. Traces are ordered newest first; spans are ordered by sequence.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/projects/{id}/observability/` | GET | Dashboard aggregates and facets |
| `/api/v1/projects/{id}/observability/traces/` | GET | Paginated trace list (50/page) |
| `/api/v1/observability/traces/{id}/` | GET | Trace detail, request/response and spans |

Query parameters accepted by the dashboard and list:

| Parameter | Meaning |
|---|---|
| `from`, `to` | ISO date or timestamp; a date-only `to` includes the whole day |
| `provider` | Provider UUID |
| `model` | Exact model id |
| `status` | `succeeded` or `failed` |
| `source` | `playground` or `evaluation` |
| `role` | `model` or `judge` |

Invalid parameters return a 400 with a field error. Viewers can read all
observability data in their workspace; no mutation endpoint exists. The
dashboard response also includes `rollups.through` (the last aggregated day),
`rollups.from`/`to` (the rolled-up portion of this query) and
`rollups.retention_days`.

## Retention and rollups

Completed days are rolled up by `apps.observability.maintain`, scheduled daily
at 01:15 through Celery Beat, or manually:

```text
python manage.py rollup_traces --through 2026-11-08
python manage.py purge_traces --days 30
```

The dashboard uses rollups for days up to the project watermark and raw traces
for newer days. A raw date range is excluded from aggregation once its whole
day is covered, so the two sources never add the same call twice. Partial
timestamp filters keep the boundary day raw.

| Setting | Default | Meaning |
|---|---|---|
| `OBSERVABILITY_ROLLUP_ENABLED` | `true` | Build rollups and schedule maintenance |
| `OBSERVABILITY_TRACE_RETENTION_DAYS` | `0` | Delete raw traces older than this many complete days; `0` keeps them forever |

Retention rolls up the affected project first and skips deletion for that
project if the rollup fails. Rollup rows are retained regardless of raw-trace
retention, so historical dashboard totals survive after raw rows are removed.
`purge_traces --days` can override the configured value for one run. The
trace explorer and slowest-call list only have raw records available, so those
views intentionally show only retained traces.

## Benchmark

The benchmark creates an isolated temporary workspace and deletes it afterward;
it never adds synthetic rows to an existing project:

```text
python manage.py benchmark_observability \
  --email owner@example.com \
  --days 365 --models 20 --providers 4 --raw-traces 10000 --runs 3
```

At the defaults it creates 233,600 rollup buckets representing about 23.4
million calls, plus 10,000 current-day raw traces. It measures the same
`services.dashboard` path used by the API and reports database query counts,
min/median/p95/max latency, calls represented and the rollup watermark.

The local reference run used SQLite with 233,600 rollup rows and 10,000 raw
traces: **33 queries on every run**, median **8.47 s** (min 7.85 s, max 8.77 s)
for all 23.37 million calls. SQLite's group-by is the limiting factor here; this
is not a PostgreSQL production measurement. The query count is fixed and is
covered by a regression test.

## Cost policy

A cost is produced only when **all** of these are true:

1. the provider reported both input and output token counts;
2. `EXECUTION_PRICING` contains an explicit entry for
   `"<provider kind>:<model id>"` (or a provider-kind default);
3. that entry has non-negative `input_per_million`, `output_per_million` and a
   currency.

The formula is `input_tokens / 1,000,000 * input_per_million +
output_tokens / 1,000,000 * output_per_million`, quantized to six decimal
places. Otherwise the trace stores `cost_status=unavailable` and a reason, and
the dashboard says **Unavailable** rather than displaying `$0` or a guessed
value. Partial coverage is shown as `partial` with the number of calls that
could and could not be estimated. Local models remain unavailable unless the
operator explicitly supplies a price.

There are no built-in vendor prices. `EXECUTION_PRICING` is documented in
`.env.example` with its JSON shape and no example amounts.

## Evaluation and Playground integration

- **Playground** (`apps/playground/services.py`): `_prepare` and `_generate`
  are timed; a successful or failed call creates one trace. The provider
  request is wrapped in an OTel span; preparation and the request are stored as
  spans. The linked result is updated with the estimate when one exists.
  A failed provider call now produces a failed result and failed trace instead
  of an unhandled exception.
- **Evaluation** (`apps/evaluations/services.py`): each case result creates a
  trace with `provider.prepare`, `provider.generate`, `metrics.evaluate` and
  per-metric child spans. Metric failures are recorded on their own spans
  without failing the case. If the provider fails before a result exists, a
  failed trace is still recorded against the case.
- **Judge** (`integrations/evaluation/judge.py`): the adapter's `on_call` hook
  is invoked for every judge call, producing a `role=judge` trace linked to the
  case. The existing judge-call count on the evaluation remains the aggregate;
  the trace preserves per-call latency, tokens, prompt, response and error.
- **Comparisons** use the same Playground execution and provider path, so each
  compared model produces its own trace and links to its own result.

## Dashboard and explorer

The dashboard (`frontend/src/app/features/observability/observability.component.ts`)
shows:

- total executions with model/judge split;
- succeeded/failed and failure rate;
- average provider latency;
- input/output tokens and how many calls reported usage;
- estimated cost with status `estimated`, `partial` or `unavailable`;
- a daily execution trend split by success/failure;
- model usage table (calls, failures, average latency, tokens, cost);
- provider usage, error categories and slowest calls;
- recent traces with role, status, latency and link to the explorer.

Filters are date inputs, provider/model/status/source/role selects and a reset
action. Facets come from the full project trace set so a filter cannot hide the
other options. The Explorer page shows total duration and provider latency
separately, tokens, cost explanation, OTel trace id, source request/response,
and every span in start order with parentage, duration, attributes and errors.

## Verification

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest -q` in `backend/` | **120 passed** (8 API + 7 rollup/retention + 2 benchmark tests) |
| Django configuration | `manage.py check --settings=config.settings.test` | no issues |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Frontend build | `npx ng build` | success (Observability 22.26 kB, trace detail 9.10 kB lazy chunks) |
| Frontend specs | `npx ng test --watch=false --browsers=ChromeHeadless` | **21 passed** (3 new) |
| Live end-to-end | Playground + Django API + separate Celery worker + Ollama-contract stub + Angular UI | pass |

### Automated coverage

`backend/tests/test_observability_api.py` covers:

- trace creation linked to a Playground result, including status, provider,
  model, timing, tokens and cost;
- span parent/child relationships and ordering;
- failed execution error recording and unavailable cost;
- token totals and cost calculation from explicit pricing;
- dashboard filters by status, provider and model;
- workspace permission isolation and cross-workspace 404;
- evaluation traces and metric child spans;
- judge trace role and linkage;
- cascade cleanup of traces and spans when their linked evaluation is deleted.

`backend/tests/test_observability_rollups.py` covers:

- no double counting when old traces come from rollups and current traces come
  from raw rows;
- filters, costs, token totals and error categories surviving raw retention;
- idempotent rebuilds;
- disabled retention and disabled rollups, including refusing to delete raw
  traces when rollups are disabled;
- retention refusing to delete when a rollup fails;
- the management commands.

`backend/tests/test_observability_benchmark.py` covers:

- bounded query counts against a seeded rollup-backed dashboard;
- actual rollup-table reads rather than one query per raw trace/group;
- the benchmark command creating and cleaning up its temporary workspace.

The two frontend specs cover dashboard rendering of totals, usage, trend,
recent traces and unavailable costs, plus trace-detail rendering of the
request, response, OTel id and nested spans.

### Live workflow exercised

The live check used a fresh SQLite database with `config.settings.livecheck`,
a separate Celery worker, a local HTTP stub implementing the Ollama contract,
and the Angular dev server:

- Playground call `Say hello.` with `llama3.2`: succeeded, response
  `Reply from llama3.2`, 12 input / 8 output tokens, two spans
  (`provider.prepare`, `provider.generate`), OTel trace id captured, estimated
  cost `0.000025 USD`.
- Playground call `Please fail.` with `broken-model`: failed with
  `provider_error`, no tokens, cost `unavailable`.
- Evaluation over the two-record dataset with `llama3.2` and `exact_match` /
  `token_f1`: completed 2/2 case results, each with an evaluation trace, a
  `metrics.evaluate` span and per-metric child spans, responses `4` and
  `Paris`.
- Dashboard read-back: **4 calls, 3 succeeded, 1 failed, 36 input / 24 output
  tokens, 0.000075 USD estimated for 3 calls, cost_status `partial`**, error
  category `provider_error`, telemetry enabled.
- Trace list and detail read-back through the API and Angular UI; the detail
  page displayed the request, response, tokens, OTel id and all five
  evaluation spans. Selecting `status=failed` reduced the dashboard to 1 call,
  0 succeeded / 1 failed and `Unavailable` tokens and cost. No console errors
  were produced.

## Limitations

- **No local PostgreSQL/Redis.** Tests and the live check used SQLite; the live
  worker used Celery's filesystem broker. Compose still targets PostgreSQL and
  Redis, and a run on that stack remains to be done. `pywin32` was only needed
  for the Windows filesystem broker.
- **The live model was a local stub**, not a real hosted model. Z.ai execution
  still requires a user-supplied key. The stub returns fixed token counts and
  deterministic text, so latency and cost figures demonstrate the plumbing, not
  provider performance.
- **No OTLP collector was running.** OTel spans and trace ids were created
  in-process; the OTLP/HTTP exporter path is implemented but was not exercised
  against a collector. Database traces do not depend on it.
- **Judge traces require the judge metrics to run.** The live dataset used only
  built-in metrics, so judge traces and judge prompts/responses are covered by
  tests rather than the live run. Judge metrics also require schema-valid JSON
  from the chosen model.
- **Costs are estimates and only as good as the supplied price.** Prices are
  operator configuration; there is no automatic price feed and no currency
  conversion. Costs are unavailable for any call without both token counts and
  a complete price entry.
- **Rollups cover complete UTC days only.** Today remains on raw traces until
  the next maintenance run. Celery Beat must be running for automatic rollups;
  otherwise use the management commands. A first backfill of a large history can
  take time.
- **Slowest calls and the trace explorer need raw rows.** After raw retention
  removes a trace, its aggregate remains on the dashboard but the individual
  trace and span tree are gone. The trace explorer does not reconstruct old
  traces from rollups.
- **Retention is opt-in.** `OBSERVABILITY_TRACE_RETENTION_DAYS=0` is the safe
  default; operators must choose a positive window to bound the raw table.
- **Polling, not streaming.** The dashboard has a manual Refresh button and
  reads on load/filter change; there is no websocket or push update. Metrics
  and alert thresholds are not configurable, and there is no alert delivery.
- **Trace links follow the source record.** Deleting a linked execution or
  evaluation result (or its project) deletes the trace and its spans rather than
  leaving an orphan that can no longer show the request/response. Provider
  deletion is different: the trace keeps the provider name/kind snapshot and
  only the optional provider reference becomes null.
