# Milestone 5 — Datasets and Evaluation

Date: 2026-11-09 · Status: **complete against its exit criteria** (a repeatable
two-model evaluation ran through a real Celery worker, and both per-case results
and the aggregate summary were read back from the database)

## Delivered

- **Dataset management** — create, list, rename, describe and delete datasets
  per project. A dataset's `version` increases on every record change.
- **File import** — JSON, JSONL and CSV (header row). Imports are validated row
  by row and applied atomically: if anything is invalid, nothing is imported and
  the response lists the failing row, field and message. Append and replace
  modes; files up to 2 MB / 500 records.
- **Record management** — inspect paginated records, add, edit and delete a
  single case with `input`, optional `expected_output`, retrieval `context` and
  free-form `metadata`.
- **Metric registry** — one catalogue endpoint (`/evaluation-metrics/`) that
  reports exactly what the platform can compute. Pages never hardcode metric
  logic.
- **Evaluations** — choose a dataset, one to five models, metrics, optional
  inference parameters and (for judge metrics) a judge model.
- **Background execution** — every run is queued through Celery
  (`apps.evaluations.run_evaluation`) and moves through `queued → running →
  completed | failed`. Queue failures are surfaced on the run instead of being
  lost.
- **Per-case persistence** — each model/dataset-record pair becomes an
  `EvaluationResult` row with the frozen input, expected answer and context, the
  generated response, latency, tokens, every metric score/reason/error, and the
  case error if the model failed.
- **Summaries** — per-model aggregate scores, per-metric scored counts, success
  and failure counts, average latency and token totals, plus overall totals and
  judge-call count.
- **Inspection and comparison** — results are filterable by model and status,
  expandable per case, and model summaries sit side by side for the same
  dataset.
- **Repeatable runs** — creating a run again or hitting `rerun` always creates a
  new evaluation from the same frozen case snapshots; previous runs are never
  modified, and reruns still work after the dataset is edited or deleted.
- **Datasets and Evaluations pages** in the Angular app, with live polling while
  a run is queued/running.

## Metric registry

| Key | Source | Needs | Notes |
|---|---|---|---|
| `exact_match` | built-in | expected answer | Normalised comparison (case, punctuation, articles, whitespace) |
| `contains_match` | built-in | expected answer | Expected answer contained in the response |
| `token_f1` | built-in | expected answer | Word-overlap F1 |
| `answer_relevancy` | DeepEval 4.3 | judge model | `AnswerRelevancyMetric`, threshold 0.5 |
| `faithfulness` | DeepEval 4.3 | context + judge model | `FaithfulnessMetric`, threshold 0.5 |
| `contextual_relevancy` | DeepEval 4.3 | context + judge model | `ContextualRelevancyMetric`, threshold 0.5 |

Judge metrics are listed only when DeepEval is installed **and**
`EVALUATION_JUDGE_METRICS_ENABLED` is on. Missing expected answers, missing
context or a failing judge never fail the run: they are recorded as that
metric's error for that case, and the model's response and other scores are
kept.

The DeepEval judge is a `DeepEvalBaseLLM` adapter that calls the project's own
provider configuration through `adapter_for` — the same M3 integration the
playground uses. No second model-execution path and no vendored SDK response.

## API

| Endpoint | Methods |
|---|---|
| `/api/v1/projects/{id}/datasets/` | GET, POST |
| `/api/v1/datasets/{id}/` | GET, PATCH, DELETE |
| `/api/v1/datasets/{id}/records/` | GET (paginated), POST |
| `/api/v1/datasets/{id}/import/` | POST (multipart `file`, `mode=append|replace`) |
| `/api/v1/dataset-records/{id}/` | GET, PATCH, DELETE |
| `/api/v1/evaluation-metrics/` | GET |
| `/api/v1/projects/{id}/evaluations/` | GET, POST |
| `/api/v1/evaluations/{id}/` | GET |
| `/api/v1/evaluations/{id}/results/` | GET (paginated, `model`, `status`) |
| `/api/v1/evaluations/{id}/rerun/` | POST |

`Evaluation.total_cases` counts dataset records; `total_results` counts
model/record pairs, which is what progress uses (`completed_cases` increments
per result row).

## Access rules

- Viewers read datasets, records, evaluations and results, but cannot modify or
  start anything.
- Members create datasets and records, import files and start/rerun
  evaluations; they may edit datasets they created.
- Admins and owners may edit any dataset in the workspace.
- Cross-tenant access returns 404, matching the existing tenancy rules.

## Decisions

- **Frozen snapshots.** Record text is copied into result rows when the run is
  created, and `dataset_version` is stored on the evaluation. Editing a dataset
  after a run cannot change history, and reruns replay the original snapshot
  rather than the current dataset.
- **Progress is per case result.** A run of 2 models over 3 records has 6 case
  results; the UI shows `6 of 6 case results` with the record count alongside.
- **Metric failures are data.** A missing expected answer or judge failure is
  stored per metric so one metric cannot discard a model answer.
- **Runs are immutable.** No endpoint edits an existing evaluation or result;
  repetition means a new run.
- **Failures are isolated per model.** A model whose provider fails still gets
  result rows with its error, and the other model's results are unaffected.

## Verification

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` (in `backend/`) | **103 passed** (36 new for M5) |
| Django configuration | `manage.py check --settings=config.settings.test` | no issues |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Frontend build | `ng build` | success (Datasets 20.4 kB, Evaluations 30.4 kB lazy chunks) |
| Frontend specs | `ng test --watch=false --browsers=ChromeHeadless` | **18 passed** (4 new) |
| Live end-to-end | Django API + **separate Celery worker** + Angular UI + local Ollama-contract stub | pass |

### Live workflow exercised

- 3-record dataset imported through the public API, 4th record imported through
  the Datasets page's file input.
- Evaluation with `llama3.2` and `second-model` over `exact_match`, `token_f1`
  and `answer_relevancy` (judge model `judge-model`): status went `queued →
  running → completed`, 6/6 case results succeeded, per-case responses `4` and
  `Paris`, averages `1.0` for all three metrics, 18 judge calls.
- Records without an expected answer stored the metric error and still
  succeeded for the response and remaining metrics.
- `rerun` created a second evaluation with the same 3 records and 6 results;
  the original kept its status, counts and completion timestamp.
- Starting an evaluation from the Evaluations page produced a 4/4 run with a
  per-model average of `0.67`; expanding a case showed the frozen input, “Not
  provided” expected answer, response and the exact metric error.
- Database read-back confirmed `Evaluation` rows plus 6 `EvaluationResult` rows
  (all `succeeded`) and metric scores on the stored rows.

## Limitations

- **PostgreSQL/Redis were not available on this machine.** Unit/API tests use
  SQLite, and the live check used SQLite with Celery's filesystem broker (a real
  separate worker process). Compose still points at PostgreSQL 16 + Redis 7; a
  run on that stack remains to be done. `pywin32` was needed only for the
  Windows filesystem broker in the live check and is not a runtime dependency.
- Judge metrics depend on the chosen model returning schema-valid JSON; a
  non-compliant model records a metric error per case rather than a score.
- Judge metrics cost additional model calls (18 for six case results above).
- The live check used a stub that implements the Ollama contract, not a real
  model; Z.ai execution still needs a real key.
- Datasets expose a version number but not a browsable per-version diff; runs
  keep the authoritative snapshot.
- Costs per evaluation are not tracked, for the same reason as M4: providers
  report no pricing.
