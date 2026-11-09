# Milestone 8 — Analytics and Reporting

Status: **complete against its exit criteria** — the analytics dashboard reads real
Playground, trace, evaluation and security records; date/provider/model/source
filters were exercised against the live API and UI; and a report was generated
from the UI and exported successfully as both CSV and PDF.

## What was built

The analytics feature reuses the existing records rather than maintaining a
second analytics store:

- `Execution` and `ExecutionResult` for Playground activity, model calls,
  token counts and stored execution costs.
- `Trace` and `TraceRollup` for provider latency, token usage, costs and daily
  performance history. Analytics calls the observability filter/window helpers
  internally so the dashboard and model history count the same calls.
- `Evaluation` and `EvaluationModel` for evaluation runs, model scores and
  per-model historical evaluation scores.
- `SecurityScan` and `SecurityFinding` for security activity and findings.

`AnalyticsReport` is the only new persisted model. It stores the report title,
selected sections, period, filters, workspace/project scope and a snapshot of
the generated data. This is required for reproducibility; it is not a parallel
analytics database.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/projects/{project_id}/analytics/` | Dashboard summary, filters, usage, costs, evaluation history, security activity and daily trends |
| `GET /api/v1/projects/{project_id}/analytics/models/` | Per-model performance history and comparison data |
| `GET/POST /api/v1/projects/{project_id}/analytics/reports/` | List stored reports / generate a report snapshot |
| `GET /api/v1/analytics-reports/{report_id}/` | Report metadata and rendered document sections |
| `GET /api/v1/analytics-reports/{report_id}/export/?export_format=csv` | CSV export of the stored snapshot |
| `GET /api/v1/analytics-reports/{report_id}/export/?export_format=pdf` | PDF export of the stored snapshot |

`export_format` is used instead of `format` because DRF reserves `format` for
content negotiation.

Dashboard query parameters are `from`, `to`, `provider`, `model` and `source`.
`from` and `to` are inclusive calendar dates in UTC; the default period is the
last 30 days. `provider` is a project provider UUID. `model` is the stored
provider model identifier. `source` is `playground` or `evaluation`.

## Calculations and honesty rules

- **Model calls** are trace records with the `model` role. Succeeded and failed
  calls come from trace status; partial/failed Playground executions are
  reported separately.
- **Token totals** sum only reported token values. `token_calls` and
  `calls_without_tokens` are exposed so a total is never presented as complete
  when it is not.
- **Average latency** is the mean provider-reported latency, not full span
  duration. The dashboard also exposes the full duration where available.
- **Costs** use only stored estimated-cost values with explicit currency. Calls
  with missing pricing or missing token data are counted as unavailable. The
  API returns `partial`/`unavailable` status and an explanatory detail; it never
  turns missing cost data into zero.
- **Evaluation scores** are the mean of available stored metric averages for
  completed evaluation runs. Different metrics can therefore be combined; this
  is documented in the API response.
- **Security counts** are period-wide and intentionally unaffected by provider
  and model filters, because dataset and prompt scans are not tied to a model.
  The API returns a scope note stating this.
- **Daily history** uses persisted daily rollups for completed days and raw
  traces for the live edge. The observability window prevents the boundary day
  from being counted twice.

## Reports and exports

Reports snapshot the dashboard and model-performance data at generation time.
The snapshot preserves:

- workspace and project names and identifiers;
- the exact reporting period and timezone;
- provider, model and source filters;
- selected sections;
- generation and data-capture timestamps;
- limitations and scope notes.

Exports are built only from that snapshot, so a later execution cannot silently
change an old report. CSV is a flat `section,item,value` document with labels,
period, timestamps and section summaries. PDF renders the same labelled
sections with page numbering. The PDF writer is a small dependency-free renderer
in `integrations/reporting/pdf.py`; non-ASCII punctuation is transliterated to
plain ASCII for reliable text extraction.

Available report sections: `overview`, `usage`, `performance`, `evaluations`,
`costs`, `security` and `trends`.

## Permissions

All analytics and report endpoints require authentication. The project is
resolved through `project_for_user`, which requires workspace membership and
returns 404 for projects outside the caller's workspaces. Reports resolve the
project through their workspace before returning data, so a report ID from
another workspace is also a 404. Viewers can read analytics and reports; report
creation requires viewer access to the project. A report records its creator
and workspace/project scope for inspection.

## Angular UI

`/analytics` provides:

- summary cards for executions, model calls, success/failure, tokens, latency,
  estimated costs, evaluations and security;
- date/provider/model/source filters and reset;
- a usage and performance trend chart with tooltips;
- provider and model breakdown tables with honest cost/unavailable labels;
- model comparison with historical latency, tokens, error rate and evaluation
  scores;
- cost breakdown by currency, provider and model;
- evaluation history and security activity;
- report section selection, generation, stored-report list, preview and
  CSV/PDF downloads.

The route is lazy-loaded and linked in the main navigation.

## Automated tests

`backend/tests/test_analytics_api.py` covers:

1. Dashboard aggregation of real executions, traces, evaluations, costs and
   security records, including provider/model/source filtering, empty periods,
   validation, evaluation-only periods, workspace isolation and authentication.
2. Model performance history from rollups and live traces, including the
   boundary-day de-duplication, token/latency/cost totals and evaluation scores.
3. Report snapshot creation, rendered document sections (including model
   performance), CSV/PDF exports, snapshot stability after new data, invalid
   export formats/sections/dates, viewer access and cross-workspace isolation.
4. Missing costs remaining `unavailable` rather than becoming zero, with the
   default provider/model labels in report metadata.

Verification run at completion:

| Check | Result |
|---|---|
| `cd backend && .venv/Scripts/python.exe -m pytest -q` | 143 passed |
| `cd backend && .venv/Scripts/python.exe -m pytest -q tests/test_analytics_api.py` | 4 passed |
| Django system check (`config.settings.test`) | passed |
| `makemigrations --check --dry-run` | no changes detected |
| `cd frontend && npx ng build` | passed; analytics lazy chunk 37.86 kB |
| `cd frontend && npx ng test --watch=false --browsers=ChromeHeadless` | 21 specs passed |
| Live `/analytics` on the preview workspace | real data displayed; filters produced scoped totals |
| Live report generation + CSV/PDF download | generated report `bf8844cb-bfdc-46fa-ac8d-a21adc78b76a`; valid 9-page PDF extracted with `pdftotext` (the preview retains this clean report) |

The live preview database contained 5,761 model calls (2,880 succeeded, 2,881
failed), 2 Playground executions, 0 evaluation runs and 7 security scans with
27 findings. The evaluation card therefore honestly showed `0` and an
unavailable mean score; no evaluation figures were fabricated to make the
dashboard look fuller.

## Limitations

- Estimated costs remain partial when any call lacks explicit pricing or token
  data. The live preview showed 5,760 of 5,761 calls priced, with status
  `partial`.
- Evaluation scores depend on the metrics stored by M5 and only cover completed
  runs. A workspace with no evaluation history correctly shows no score.
- Security analytics cannot be filtered by provider/model because scans can
  target datasets and prompts as well as executions.
- Daily history is limited by the observability raw-trace retention window;
  completed days already aggregated into rollups remain available.
- Reports are snapshots by design. They do not refresh automatically when new
  executions or findings arrive.
- PDF exports are text summaries with page numbering, not embedded dashboard
  charts. CSV exports are flat rows rather than a multi-sheet workbook.
- The live checks used the SQLite preview database and a local preview backend;
  live PostgreSQL was not exercised for this milestone.
