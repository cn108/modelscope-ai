# Datasets and evaluation

Evaluation is a two-part workflow: a **dataset** holds test cases, and an **evaluation
run** applies one or more metrics to one or more models. Runs are asynchronous and
persist immutable per-case results.

## Datasets

A dataset belongs to one project. Dataset names are unique within a project. The platform
supports manual record management and validated file imports.

### Record shape

| Field | Required | Limits | Meaning |
|---|---|---|---|
| `input` | yes | 20,000 chars | The user/question input sent to the model. |
| `expected_output` | no | 20,000 chars | Reference answer for reference metrics. |
| `context` | no | 60,000 chars total | Retrieval context; string or list of strings. |
| `metadata` | no | 4 KB serialized JSON | Caller-defined labels; not sent to the model. |

A record is stored with a position. Creating/updating/deleting records increments the
dataset version. Evaluation result rows copy the record content, so later edits do not
rewrite an existing run.

### Import formats

#### JSON

A top-level array, or an object with a `records` array:

```json
{
  "records": [
    {
      "input": "What is the capital of France?",
      "expected_output": "Paris",
      "context": ["France's capital is Paris."],
      "metadata": {"split": "smoke"}
    }
  ]
}
```

#### JSONL / NDJSON

One JSON object per line:

```jsonl
{"input":"What is 2+2?","expected_output":"4","context":["Two plus two equals four."]}
{"input":"What is the capital of France?","expected_output":"Paris"}
```

#### CSV

The header must contain `input` and may contain `expected_output`, `context`, `metadata`.
Unsupported columns are rejected.

```csv
input,expected_output,context,metadata
"What is 2+2?","4","Two plus two equals four.","{""split"":""smoke""}"
```

CSV `context` can be:

- a plain string;
- a JSON array of strings, for example `["Doc A", "Doc B"]`;
- multiple context strings separated by `||`.

CSV `metadata` must be a JSON object.

### Import rules

- UTF-8 text only (a UTF-8 BOM is accepted).
- Allowed extensions: `.json`, `.jsonl`, `.ndjson`, `.csv`.
- Maximum 500 records per import.
- Maximum 50 reported row errors; the total error count is still returned.
- Imports are **all-or-nothing**. If any row is invalid, nothing is imported and row-level
  errors are returned.
- `mode=append` adds records after the current highest position.
- `mode=replace` deletes existing records first, then imports from position 1.
- Both modes increment the dataset version once on success.

Example import:

```bash
curl -sS -X POST "http://localhost:8000/api/v1/datasets/$DATASET_ID/import/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@cases.jsonl" \
  -F "mode=append"
```

```json
{"imported": 25, "version": 2, "mode": "append"}
```

## Available metrics

The metric registry exposes only metrics that can actually execute. DeepEval judge
metrics disappear when `EVALUATION_JUDGE_METRICS_ENABLED=false` or DeepEval is not
installed. List the current catalogue with:

```bash
curl -sS http://localhost:8000/api/v1/evaluation-metrics/ \
  -H "Authorization: Bearer $TOKEN"
```

### Reference metrics (no judge model)

| Key | Definition | Pass rule | Requirements |
|---|---|---|---|
| `exact_match` | Normalise prediction and reference, then require equality. Normalisation lowercases, replaces punctuation with spaces, removes standalone articles (`a`, `an`, `the`) and collapses whitespace. | `1.0` only; otherwise `0.0`. | `expected_output`. |
| `contains_match` | Normalise both; score `1.0` when the normalised reference appears inside the normalised prediction. | `1.0` only. | `expected_output`. |
| `token_f1` | SQuAD-style token-overlap F1 using a multiset of normalised tokens. Word order is ignored. | Score is stored; reference metric pass rule is `score >= 1.0`. | `expected_output`. |
| `factual_correctness` | Lexical overlap plus numeric-fact recall against the reference. This is a heuristic, **not proof of truth**. | `score >= 0.5`. | `expected_output`. |
| `context_precision` | Average lexical relevance of each retrieved passage to the query/reference. | `score >= 0.5`. | `context`. |
| `context_recall` | Fraction of reference content terms present in retrieved context. | `score >= 0.5`. | `context` + `expected_output`. |
| `toxicity` | Lexicon-based screen; `1` clean, `0` strongly toxic. Bounded heuristic, not a safety guarantee. | `score >= 0.8`. | None. |

If a required field is missing, the metric result records an error instead of a score.
The model's response is still stored. Each result records the metric implementation
version so comparisons across metric changes are explicit.

### DeepEval judge metrics

| Key | Definition | Threshold | Requirements |
|---|---|---|---|
| `answer_relevancy` | How directly the response addresses the input. | `0.5` | A judge provider/model. |
| `faithfulness` | Whether claims in the response are supported by the record context. | `0.5` | `context` plus a judge. |
| `contextual_relevancy` | How much of the record context is relevant to the input. | `0.5` | `context` plus a judge. |

Judge metrics run DeepEval with the selected judge model. `passed` is `score >= 0.5`.
The judge's reason is retained up to 1,000 characters. Judge calls are extra model calls
and can materially increase latency and cost.

DeepEval telemetry is opted out in `integrations/evaluation/judge.py`; judge requests are
still sent to the provider the operator configures.

### Run limits

- 1–5 models per evaluation.
- Maximum 6 metrics per run.
- Each model gets one result row per dataset record.
- Metrics are evaluated per case; a metric failure does not discard the model's answer or
  stop the other metrics.

## Creating a run

```http
POST /api/v1/projects/<project-id>/evaluations/
Authorization: Bearer <token>
Content-Type: application/json

{
  "dataset": "<dataset-id>",
  "metrics": ["exact_match", "token_f1", "factual_correctness", "toxicity"],
  "models": [
    {"provider": "<provider-id>", "model_id": "llama3.2"}
  ],
  "parameters": {"temperature": 0.1},
  "judge": {
    "provider": "<provider-id>",
    "model_id": "llama3.2",
    "parameters": {"temperature": 0}
  }
}
```

Rules:

- A judge is required when any selected metric has `requires_judge`.
- A judge supplied with reference-only metrics is rejected.
- The dataset and all providers must belong to the same project.
- The dataset must have at least one record.
- The evaluation snapshots the dataset name/version, record text, metric keys, model
  selections, parameters and judge configuration at creation time.

The API returns a queued/running/completed evaluation. Poll `GET /evaluations/{id}/` and
read paginated results from `GET /evaluations/{id}/results/`.

## Result semantics

Each `EvaluationResult` contains:

- the frozen input, expected output and context;
- the model's generated response;
- latency and provider-reported token counts when available;
- per-metric scores, pass/fail and error/reason;
- a `scores` map and `metric_results` array;
- an overall result status (`pending`, `succeeded`, `failed`).

An aggregate summary is stored on the evaluation and each model selection. A model call
failure is stored as a failed result; it does not erase other models or other cases.
A judge metric failure is stored on that metric and does not crash the run.

## Reproducibility

To make a run reviewable, retain:

1. the evaluation ID and `dataset_name`/`dataset_version`;
2. the frozen input/expected/context rows;
3. the metric keys and judge model/provider/parameters;
4. the model IDs, provider names/kinds and execution parameters;
5. the application commit and dependency lockfiles;
6. the provider model version/date if the provider exposes one;
7. trace IDs and stored request/response for the run.

The rerun endpoint creates a new evaluation from the stored configuration. It does not
mutate the old run.

Reproducibility is **not guaranteed** even with the same configuration:

- model providers can update weights or serving behaviour without changing the model ID;
- sampling is not deterministic unless the provider/model honours seed and temperature;
- judge metrics depend on a model's structured output and can vary across runs;
- DeepEval/library versions affect judge prompts and scoring;
- metric implementations are versioned, but provider/judge library behavior can still
  change. The run records `metric_versions`; compare runs with the same versions, and
  retain both evaluation IDs when versions differ.

For a fair comparison, run the same dataset and configuration before and after a model or
metric change, and retain both evaluation IDs.

## Custom metric hooks

Built-in reference metrics live in `integrations/evaluation/metrics.py`; the registry
exposes a `register_metric` hook for deployment-specific scorers. A custom scorer is a
callable taking `(prediction, reference, context)` and returning a score in `[0, 1]`, with
a key, label, threshold and version. Register it at application startup; it then appears
in `/api/v1/evaluation-metrics/` and in the evaluations UI without changing the API.

## Human review and disagreement

Reviewers can label individual results `pass`, `fail` or `unsure` with an optional note
through `POST /api/v1/evaluations/{id}/results/{result_id}/reviews/`. Multiple reviewers
can review the same result; the API returns a `review_summary` with review count, reviewed
results, label counts, disagreement count and agreement rate. Reviews are not used as
ground truth or to overwrite metric scores.

## Cost and telemetry

Evaluation results store token counts reported by the provider. Cost is not summarized as
an evaluation total; individual model-call traces can carry an estimated cost when
`EXECUTION_PRICING` has a matching entry and both token counts are known. Otherwise cost
is `unavailable` rather than zero.

Each model/judge call creates a trace and span tree. Raw-trace retention is controlled by
`OBSERVABILITY_TRACE_RETENTION_DAYS`; evaluation results themselves are not deleted by
that retention setting.

## Limitations

- Datasets expose a version number but not a browsable per-version diff. The evaluation's
  copied record text is the authoritative snapshot.
- Import validation checks structure and size, not semantic quality or label correctness.
- A reference metric can be gamed by a response that copies the expected answer; it is a
  comparison aid, not a measure of reasoning.
- Judge metrics depend on the judge model returning schema-valid output. Non-compliant
  output becomes a metric error, not a pass.
- A clean evaluation does not prove safety, correctness or production readiness.
- Deleting a provider/dataset may leave historical evaluation rows with denormalised
  names/versions but broken optional links; do not delete source objects you still need
  for audit without exporting the run first.
