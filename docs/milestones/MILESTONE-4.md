# Milestone 4 — Playground, execution history and versioned prompts

Date: 2026-11-09 · Status: **complete against its exit criteria** (full workflow
exercised against a live API and the Angular UI)

## Delivered

- **Single-model runs** — select a provider and model, enter a system prompt and
  a user prompt, and execute using the Milestone 3 adapters. No separate provider
  system and no hardcoded responses exist in this layer.
- **Two-model comparison** — the same prompts run against two models
  concurrently (`ThreadPoolExecutor`); each model receives its own result row.
- **Per-model metrics** — provider-reported latency, input/output tokens and
  finish reason. Cost is stored as `null` unless a provider reports pricing, and
  is labelled "Not reported" in the UI rather than guessed.
- **Failure isolation** — a failing or misconfigured model is saved as that
  model's failed result with a redacted error. The other model's response is
  still persisted; the execution is marked `partial`.
- **Execution history** — every run is listed per project, can be reopened with
  its exact prompts and settings, and can be rerun. A rerun creates a new
  execution; the original is never modified.
- **Saved prompts** — create, edit, duplicate and delete reusable prompts.
- **Version history** — content edits append an immutable version; renames do
  not. Any version can be inspected and restored, which appends a new version
  containing the old content. Versions are never rewritten or deleted
  individually.
- **Immutable execution snapshots** — system prompt, user prompt and parameters
  are copied onto the execution at run time, along with the referenced prompt id
  and version number. Editing or deleting a saved prompt afterwards does not
  change earlier runs.
- **Angular Playground** (`/playground`) with project selector, mode toggle,
  composer, result cards, history and prompt library. The sidebar item is now a
  live route instead of a "Soon" placeholder.

## API

| Endpoint | Methods |
|---|---|
| `/api/v1/projects/{id}/prompts/` | GET, POST |
| `/api/v1/prompts/{id}/` | GET, PATCH, DELETE |
| `/api/v1/prompts/{id}/versions/` | GET |
| `/api/v1/prompts/{id}/versions/restore/` | POST |
| `/api/v1/prompts/{id}/duplicate/` | POST |
| `/api/v1/projects/{id}/executions/` | GET, POST |
| `/api/v1/executions/{id}/` | GET |
| `/api/v1/executions/{id}/rerun/` | POST |

`ProviderConfig` now includes a read-only `models` list so any workspace member
can pick known model ids in the playground without the admin-only model refresh.

## Access rules

- Viewers can read prompts, versions and executions, but cannot create, edit or
  execute.
- Members can run models and manage prompts they created; admins and owners can
  edit any prompt in the workspace.
- Cross-tenant access returns 404, matching the existing workspace rules.

## Decisions

- Prompt versions are append-only: edits and restores create new rows, so the
  audit trail is complete and records can never drift.
- Execution results are written only after provider calls complete, in one
  transaction, so a failure cannot leave a half-written execution.
- Provider adapters are built on the request thread (credential decryption
  touches the database) and only the network call runs in worker threads.
- Parameters are merged provider settings → execution parameters → per-model
  parameters, then validated against the existing inference allow-list.
- Cost is intentionally nullable: neither M3 adapter receives pricing data, so
  showing a number would be fabrication.

## Verification

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` (in `backend/`) | **67 passed** (19 new for M4) |
| Django configuration | `manage.py check --settings=config.settings.test` | no issues |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Frontend production build | `ng build` | success, Playground lazy chunk emitted |
| Frontend unit specs | `ng test --watch=false --browsers=ChromeHeadless` | **14 passed** (2 new) |
| Live API + UI workflow | Django dev server + Angular dev server + local Ollama-compatible stub | pass |

### Live workflow exercised

Registered a user, created a workspace, project and Ollama provider, listed
models, then in the browser: ran a comparison of `good-model` and `broken-model`
(result `partial`, successful content and metrics saved alongside a redacted
`HTTP 500` failure), saved a prompt (v1), edited it (v2), confirmed the earlier
run still showed the original prompt text, restored v1 (v3), duplicated the
prompt, reran a stored execution (new execution, original unchanged), and ran
again with the saved prompt referenced (execution stored `prompt_version: 3`).
All requests returned 200/201 and the browser console showed no errors.

## Limitations

- The live run used a local stub that implements the Ollama HTTP contract, not a
  real model. Z.ai execution remains unverified until a real API key is entered
  in the app.
- Cost comparison is unavailable because no provider in M3 reports pricing.
- Executions run synchronously in the API request; there is no streaming UI or
  background job queue yet.
- Reruns do not re-link the original saved prompt (the prompt snapshot is kept,
  but the new execution references no prompt), so later prompt edits cannot
  affect replays.
