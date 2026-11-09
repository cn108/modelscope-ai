import { DatePipe } from '@angular/common';
import {
  Component,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { Dataset, DatasetService } from '../datasets/dataset.service';
import { ProjectService } from '../projects/project.service';
import { ProviderConfig, ProviderService } from '../providers/provider.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  Evaluation,
  EvaluationModel,
  EvaluationResultRow,
  EvaluationService,
  MetricDefinition,
} from './evaluation.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

interface ModelRow {
  provider: string;
  modelId: string;
}

const POLL_MS = 2500;
const PAGE_SIZE = 50;

@Component({
  selector: 'msa-evaluations',
  standalone: true,
  imports: [DatePipe, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Evaluations</h1>
          <p class="msa-sub">
            Run a dataset against one or more models, scored by the platform
            metrics. Results are stored per test case and every run is kept.
          </p>
        </div>
        <label class="flex items-center gap-2 text-xs text-muted">
          <span class="whitespace-nowrap font-medium">Project</span>
          <select
            class="msa-input min-w-[220px]"
            [value]="selectedProjectId()"
            (change)="selectProject($any($event.target).value)"
            aria-label="Select project"
          >
            @for (project of projects(); track project.id) {
              <option [value]="project.id">
                {{ project.workspaceName }} · {{ project.name }}
              </option>
            }
          </select>
        </label>
      </header>

      @if (error()) {
        <p class="msa-card mt-5 flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }
      @if (notice()) {
        <p class="msa-card mt-5 flex items-start gap-2 border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700" role="status">
          <msa-icon name="check-circle" [size]="16" />
          <span>{{ notice() }}</span>
        </p>
      }

      @if (loading()) {
        <div class="mt-6 grid gap-4 xl:grid-cols-[360px_1fr]">
          <div class="msa-card p-5">
            <div class="msa-skeleton h-3 w-28"></div>
            <div class="msa-skeleton mt-4 h-9 w-full"></div>
            <div class="msa-skeleton mt-2 h-9 w-full"></div>
            <div class="msa-skeleton mt-2 h-20 w-full"></div>
          </div>
          <div class="msa-card p-5">
            <div class="msa-skeleton h-4 w-40"></div>
            <div class="msa-skeleton mt-4 h-28 w-full"></div>
          </div>
        </div>
      } @else if (!projects().length) {
        <div class="msa-card mt-6 flex flex-col items-center p-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand">
            <msa-icon name="check-circle" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            Evaluations need a project with a dataset and a configured provider.
          </p>
        </div>
      } @else {
        <div class="mt-6 grid gap-4 xl:grid-cols-[360px_1fr]">
          <div class="space-y-4">
            <section class="msa-card p-4">
              <h2 class="msa-section-title">New evaluation</h2>

              @if (!datasets().length || !providers().length) {
                <p class="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                  @if (!datasets().length) {
                    This project has no datasets yet. Upload test cases on the
                    Datasets page first.
                  } @else {
                    This project has no providers yet. Add one in Workspaces.
                  }
                </p>
              } @else {
                <div class="mt-3 space-y-3">
                  <div>
                    <label class="msa-label" for="evaluation-dataset">Dataset</label>
                    <select
                      id="evaluation-dataset"
                      class="msa-input"
                      [value]="datasetId()"
                      (change)="datasetId.set($any($event.target).value)"
                    >
                      @for (dataset of datasets(); track dataset.id) {
                        <option [value]="dataset.id">
                          {{ dataset.name }} (v{{ dataset.version }}, {{ dataset.record_count }} cases)
                        </option>
                      }
                    </select>
                  </div>

                  <div>
                    <div class="flex items-center justify-between">
                      <span class="msa-label mb-0">Models</span>
                      <button
                        type="button"
                        class="msa-btn-ghost"
                        [disabled]="modelRows().length >= 5"
                        (click)="addModelRow()"
                      >
                        <msa-icon name="plus" [size]="13" /> Add model
                      </button>
                    </div>
                    <div class="mt-1 space-y-2">
                      @for (row of modelRows(); track $index; let index = $index) {
                        <div class="rounded-lg border border-line bg-canvas/40 p-2">
                          <div class="flex items-center justify-between gap-2">
                            <span class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                              Model {{ index + 1 }}
                            </span>
                            @if (modelRows().length > 1) {
                              <button
                                type="button"
                                class="msa-icon-btn text-rose-600"
                                title="Remove model"
                                (click)="removeModelRow(index)"
                              >
                                <msa-icon name="close" [size]="13" />
                              </button>
                            }
                          </div>
                          <div class="mt-1 space-y-1.5">
                            <select
                              class="msa-input"
                              [value]="row.provider"
                              (change)="setRowProvider(index, $any($event.target).value)"
                              aria-label="Provider"
                            >
                              @for (provider of providers(); track provider.id) {
                                <option [value]="provider.id">{{ provider.name }}</option>
                              }
                            </select>
                            <input
                              class="msa-input"
                              placeholder="Model id"
                              [attr.list]="'model-options-' + index"
                              [value]="row.modelId"
                              (input)="setRowModel(index, $any($event.target).value)"
                              aria-label="Model id"
                            />
                            <datalist [id]="'model-options-' + index">
                              @for (model of modelsFor(row.provider); track model.model_id) {
                                <option [value]="model.model_id">{{ model.display_name }}</option>
                              }
                            </datalist>
                          </div>
                        </div>
                      }
                    </div>
                  </div>

                  <div>
                    <span class="msa-label">Metrics</span>
                    <div class="space-y-1.5">
                      @for (metric of metrics(); track metric.key) {
                        <label class="flex cursor-pointer items-start gap-2 rounded-lg border border-line p-2 text-xs hover:bg-canvas/60">
                          <input
                            type="checkbox"
                            class="mt-0.5"
                            [checked]="selectedMetrics().includes(metric.key)"
                            (change)="toggleMetric(metric.key)"
                          />
                          <span class="min-w-0">
                            <span class="flex flex-wrap items-center gap-1">
                              <span class="font-medium text-ink">{{ metric.label }}</span>
                              <span class="msa-badge bg-slate-50 text-slate-500">
                                {{ metric.source === 'deepeval' ? 'DeepEval' : 'Built-in' }}
                              </span>
                              @if (metric.requires_expected_output) {
                                <span class="msa-badge bg-amber-50 text-amber-700">needs expected</span>
                              }
                              @if (metric.requires_context) {
                                <span class="msa-badge bg-violet-soft text-violet">needs context</span>
                              }
                              @if (metric.requires_judge) {
                                <span class="msa-badge bg-brand-soft text-brand">judge</span>
                              }
                            </span>
                            <span class="mt-0.5 block text-[11px] text-slate-500">
                              {{ metric.description }}
                            </span>
                          </span>
                        </label>
                      }
                    </div>
                  </div>

                  @if (judgeRequired()) {
                    <div class="rounded-lg border border-brand/30 bg-brand-soft/40 p-2">
                      <p class="text-[11px] font-semibold text-brand">
                        Judge model for DeepEval metrics
                      </p>
                      <div class="mt-1.5 space-y-1.5">
                        <select
                          class="msa-input"
                          [value]="judgeProvider()"
                          (change)="judgeProvider.set($any($event.target).value)"
                          aria-label="Judge provider"
                        >
                          @for (provider of providers(); track provider.id) {
                            <option [value]="provider.id">{{ provider.name }}</option>
                          }
                        </select>
                        <input
                          class="msa-input"
                          list="judge-model-options"
                          placeholder="Judge model id"
                          [value]="judgeModel()"
                          (input)="judgeModel.set($any($event.target).value)"
                          aria-label="Judge model id"
                        />
                        <datalist id="judge-model-options">
                          @for (model of modelsFor(judgeProvider()); track model.model_id) {
                            <option [value]="model.model_id">{{ model.display_name }}</option>
                          }
                        </datalist>
                      </div>
                    </div>
                  }

                  <div class="grid grid-cols-2 gap-2">
                    <div>
                      <label class="msa-label" for="eval-temperature">Temperature</label>
                      <input
                        id="eval-temperature"
                        type="number"
                        min="0"
                        max="2"
                        step="0.1"
                        class="msa-input"
                        placeholder="Default"
                        [value]="temperature()"
                        (input)="temperature.set($any($event.target).value)"
                      />
                    </div>
                    <div>
                      <label class="msa-label" for="eval-max-tokens">Max tokens</label>
                      <input
                        id="eval-max-tokens"
                        type="number"
                        min="1"
                        step="1"
                        class="msa-input"
                        placeholder="Default"
                        [value]="maxTokens()"
                        (input)="maxTokens.set($any($event.target).value)"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    class="msa-btn-primary w-full justify-center"
                    [disabled]="starting()"
                    (click)="startEvaluation()"
                  >
                    <msa-icon [name]="starting() ? 'refresh' : 'play'" [size]="15" />
                    {{ starting() ? 'Starting…' : 'Start evaluation' }}
                  </button>
                </div>
              }
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <h2 class="msa-section-title">Runs</h2>
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ evaluations().length }}
                </span>
              </div>
              @if (evaluations().length) {
                <ul class="divide-y divide-line">
                  @for (run of evaluations(); track run.id) {
                    <li>
                      <button
                        type="button"
                        class="w-full px-4 py-3 text-left"
                        [class]="selectedEvaluationId() === run.id ? 'bg-brand-soft/40' : ''"
                        (click)="selectEvaluation(run.id)"
                      >
                        <span class="flex items-center justify-between gap-2">
                          <span class="min-w-0 truncate text-sm font-medium text-ink">
                            {{ run.dataset_name }} v{{ run.dataset_version }}
                          </span>
                          <span class="msa-badge" [class]="statusClass(run.status)">
                            {{ run.status }}
                          </span>
                        </span>
                        <span class="mt-1 block text-[11px] text-slate-400">
                          {{ run.created_at | date: 'medium' }} ·
                          {{ run.models.length }} model{{ run.models.length === 1 ? '' : 's' }} ·
                          {{ run.completed_cases }}/{{ run.total_results }} case results
                        </span>
                      </button>
                    </li>
                  }
                </ul>
              } @else {
                <p class="px-4 py-8 text-center text-sm text-muted">
                  No evaluations yet. Choose a dataset, models and metrics to start.
                </p>
              }
            </section>
          </div>

          @if (evaluation(); as ev) {
            <div class="space-y-4">
              <section class="msa-card p-5">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <h2 class="text-lg font-semibold tracking-tight text-ink">
                        {{ ev.dataset_name }}
                      </h2>
                      <span class="msa-badge" [class]="statusClass(ev.status)">
                        {{ ev.status }}
                      </span>
                    </div>
                    <p class="mt-1 text-xs text-muted">
                      Dataset v{{ ev.dataset_version }} · created
                      {{ ev.created_at | date: 'medium' }} ·
                      {{ ev.metrics.length }} metric{{ ev.metrics.length === 1 ? '' : 's' }}
                      @if (ev.judge) {
                        · judge {{ ev.judge.model_id }}
                      }
                    </p>
                  </div>
                  <button
                    type="button"
                    class="msa-btn-secondary"
                    [disabled]="starting() || ev.status === 'queued' || ev.status === 'running'"
                    (click)="rerun(ev)"
                  >
                    <msa-icon name="refresh" [size]="15" /> Rerun
                  </button>
                </div>

                <div class="mt-4">
                  <div class="flex items-center justify-between text-[11px] text-slate-500">
                    <span>
                      {{ ev.completed_cases }} of {{ ev.total_results }} case results
                      finished ({{ ev.total_cases }} records)
                    </span>
                    <span>{{ progress(ev) }}%</span>
                  </div>
                  <div class="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-brand to-violet transition-all"
                      [style.width.%]="progress(ev)"
                    ></div>
                  </div>
                  @if (ev.failed_cases) {
                    <p class="mt-1 text-[11px] text-rose-600">
                      {{ ev.failed_cases }} case result{{ ev.failed_cases === 1 ? '' : 's' }} failed.
                    </p>
                  }
                </div>

                @if (ev.error) {
                  <p class="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-700">
                    {{ ev.error.message }}
                  </p>
                }

                @if (ev.status === 'queued' || ev.status === 'running') {
                  <p class="mt-3 flex items-center gap-2 rounded-lg bg-canvas p-2 text-[11px] text-slate-500">
                    <msa-icon name="refresh" [size]="13" />
                    Running in the background — this view refreshes automatically.
                  </p>
                }
              </section>

              <section class="msa-card overflow-hidden">
                <div class="msa-card-header">
                  <div>
                    <h2 class="msa-section-title">Model summary</h2>
                    <p class="text-xs text-muted">
                      Averages cover cases where the metric produced a score.
                    </p>
                  </div>
                  <span class="msa-badge bg-slate-50 text-slate-500">
                    {{ ev.models.length }} model{{ ev.models.length === 1 ? '' : 's' }}
                  </span>
                </div>

                <div class="overflow-x-auto">
                  <table class="msa-table">
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Status</th>
                        <th>Cases</th>
                        <th>Avg latency</th>
                        <th>Tokens</th>
                        @for (metric of ev.metrics; track metric) {
                          <th>{{ metricLabel(metric) }}</th>
                        }
                      </tr>
                    </thead>
                    <tbody>
                      @for (model of ev.models; track model.id) {
                        <tr>
                          <td>
                            <p class="text-sm font-medium text-ink">{{ model.model_id }}</p>
                            <p class="text-[11px] text-slate-400">{{ model.provider_name }}</p>
                          </td>
                          <td>
                            <span class="msa-badge" [class]="statusClass(model.status)">
                              {{ model.status }}
                            </span>
                          </td>
                          <td class="text-xs text-slate-600">
                            {{ model.summary.succeeded ?? 0 }} /
                            {{ model.summary.cases ?? 0 }} passed
                            @if (model.summary.failed) {
                              <span class="block text-rose-600">
                                {{ model.summary.failed }} failed
                              </span>
                            }
                          </td>
                          <td class="text-xs text-slate-600">{{ latency(model) }}</td>
                          <td class="text-xs text-slate-600">{{ tokens(model) }}</td>
                          @for (metric of ev.metrics; track metric) {
                            <td class="text-xs font-medium text-ink">
                              {{ average(model, metric) }}
                            </td>
                          }
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </section>

              <section class="msa-card overflow-hidden">
                <div class="msa-card-header">
                  <div>
                    <h2 class="msa-section-title">Test-case results</h2>
                    <p class="text-xs text-muted">
                      Inputs and expected answers are the snapshot this run used.
                    </p>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <select
                      class="msa-input max-w-[190px]"
                      [value]="resultModelFilter()"
                      (change)="setResultFilters($any($event.target).value, resultStatusFilter())"
                      aria-label="Filter by model"
                    >
                      <option value="">All models</option>
                      @for (model of ev.models; track model.id) {
                        <option [value]="model.id">{{ model.model_id }}</option>
                      }
                    </select>
                    <select
                      class="msa-input max-w-[140px]"
                      [value]="resultStatusFilter()"
                      (change)="setResultFilters(resultModelFilter(), $any($event.target).value)"
                      aria-label="Filter by status"
                    >
                      <option value="">Any status</option>
                      <option value="succeeded">Succeeded</option>
                      <option value="failed">Failed</option>
                      <option value="pending">Pending</option>
                    </select>
                  </div>
                </div>

                @if (resultLoading()) {
                  <p class="px-4 py-8 text-center text-sm text-muted">Loading results…</p>
                } @else if (results().length) {
                  <div class="divide-y divide-line">
                    @for (row of results(); track row.id) {
                      <div>
                        <button
                          type="button"
                          class="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-canvas/40"
                          (click)="toggleResult(row.id)"
                        >
                          <span class="text-[11px] text-slate-400">#{{ row.record_position }}</span>
                          <span class="min-w-0 flex-1">
                            <span class="block truncate text-sm text-ink">{{ row.input }}</span>
                            <span class="block truncate text-[11px] text-slate-400">
                              {{ row.model_id }} · {{ row.generated_response || 'No response' }}
                            </span>
                          </span>
                          <span class="flex flex-wrap gap-1">
                            @for (metric of ev.metrics; track metric) {
                              <span class="msa-badge" [class]="scoreClass(row, metric)">
                                {{ metricLabel(metric) }}
                                {{ row.scores[metric] !== undefined ? row.scores[metric].toFixed(2) : '—' }}
                              </span>
                            }
                          </span>
                          <span class="msa-badge" [class]="statusClass(row.status)">
                            {{ row.status }}
                          </span>
                          <msa-icon name="arrow-right" [size]="14" />
                        </button>

                        @if (expandedResultId() === row.id) {
                          <div class="space-y-3 bg-canvas/40 px-4 pb-4 pt-1">
                            <div class="grid gap-3 lg:grid-cols-2">
                              <div class="rounded-lg bg-white p-3 ring-1 ring-line">
                                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                  Input
                                </p>
                                <p class="mt-1 whitespace-pre-wrap text-xs text-slate-700">{{ row.input }}</p>
                              </div>
                              <div class="rounded-lg bg-white p-3 ring-1 ring-line">
                                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                  Expected answer
                                </p>
                                <p class="mt-1 whitespace-pre-wrap text-xs text-slate-700">
                                  {{ row.expected_output || 'Not provided' }}
                                </p>
                              </div>
                            </div>
                            <div class="rounded-lg bg-white p-3 ring-1 ring-line">
                              <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                Model response
                              </p>
                              <p class="mt-1 whitespace-pre-wrap text-xs text-slate-700">
                                {{ row.generated_response || 'The model returned no response.' }}
                              </p>
                              @if (row.error) {
                                <p class="mt-2 rounded bg-rose-50 p-2 text-xs text-rose-700">
                                  {{ row.error.message }}
                                </p>
                              }
                            </div>
                            @if (row.context.length) {
                              <div class="rounded-lg bg-white p-3 ring-1 ring-line">
                                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                  Retrieval context
                                </p>
                                @for (passage of row.context; track $index) {
                                  <p class="mt-1 border-l-2 border-line pl-2 text-xs text-slate-600">
                                    {{ passage }}
                                  </p>
                                }
                              </div>
                            }
                            <div class="overflow-hidden rounded-lg bg-white ring-1 ring-line">
                              <table class="msa-table">
                                <thead>
                                  <tr>
                                    <th>Metric</th>
                                    <th>Score</th>
                                    <th>Result</th>
                                    <th>Detail</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  @for (metric of row.metric_results; track metric.metric) {
                                    <tr>
                                      <td class="text-xs font-medium text-ink">{{ metric.label }}</td>
                                      <td class="text-xs text-slate-600">
                                        {{ metric.score !== null ? metric.score.toFixed(3) : '—' }}
                                        @if (metric.threshold !== null) {
                                          <span class="text-slate-400">
                                            / {{ metric.threshold }}
                                          </span>
                                        }
                                      </td>
                                      <td class="text-xs">
                                        @if (metric.error) {
                                          <span class="text-rose-600">error</span>
                                        } @else if (metric.passed) {
                                          <span class="text-emerald-600">passed</span>
                                        } @else {
                                          <span class="text-amber-600">below threshold</span>
                                        }
                                      </td>
                                      <td class="max-w-[320px] text-[11px] text-slate-500">
                                        {{ metric.error || metric.reason || '—' }}
                                      </td>
                                    </tr>
                                  }
                                </tbody>
                              </table>
                            </div>
                          </div>
                        }
                      </div>
                    }
                  </div>
                  @if (resultCount() > pageSize) {
                    <div class="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-muted">
                      <span>Page {{ resultPage() }} of {{ resultPages() }}</span>
                      <div class="flex gap-2">
                        <button
                          type="button"
                          class="msa-btn-ghost"
                          [disabled]="resultPage() <= 1"
                          (click)="loadResults(resultPage() - 1)"
                        >
                          Previous
                        </button>
                        <button
                          type="button"
                          class="msa-btn-ghost"
                          [disabled]="resultPage() >= resultPages()"
                          (click)="loadResults(resultPage() + 1)"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  }
                } @else {
                  <p class="px-4 py-8 text-center text-sm text-muted">
                    No case results match this filter.
                  </p>
                }
              </section>
            </div>
          } @else {
            <div class="msa-card flex flex-col items-center justify-center p-12 text-center">
              <span class="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-400">
                <msa-icon name="check-circle" [size]="22" />
              </span>
              <p class="mt-3 text-sm font-medium text-ink">No run selected</p>
              <p class="mt-1 max-w-sm text-sm text-muted">
                Start an evaluation on the left, or open a previous run to inspect
                its scores and per-case results.
              </p>
            </div>
          }
        </div>
      }
    </div>
  `,
})
export class EvaluationsComponent implements OnInit, OnDestroy {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly providerService = inject(ProviderService);
  private readonly datasetService = inject(DatasetService);
  private readonly evaluationService = inject(EvaluationService);

  readonly pageSize = PAGE_SIZE;

  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly datasets = signal<Dataset[]>([]);
  readonly providers = signal<ProviderConfig[]>([]);
  readonly metrics = signal<MetricDefinition[]>([]);
  readonly evaluations = signal<Evaluation[]>([]);

  readonly evaluation = signal<Evaluation | null>(null);
  readonly selectedEvaluationId = signal('');
  readonly results = signal<EvaluationResultRow[]>([]);
  readonly resultCount = signal(0);
  readonly resultPage = signal(1);
  readonly resultModelFilter = signal('');
  readonly resultStatusFilter = signal('');
  readonly resultLoading = signal(false);
  readonly expandedResultId = signal<string | null>(null);

  readonly loading = signal(true);
  readonly starting = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  readonly datasetId = signal('');
  readonly modelRows = signal<ModelRow[]>([{ provider: '', modelId: '' }]);
  readonly selectedMetrics = signal<string[]>([]);
  readonly judgeProvider = signal('');
  readonly judgeModel = signal('');
  readonly temperature = signal('');
  readonly maxTokens = signal('');

  readonly judgeRequired = computed(() => {
    const selected = new Set(this.selectedMetrics());
    return this.metrics().some(
      (metric) => metric.requires_judge && selected.has(metric.key),
    );
  });

  private timer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.loadMetrics();
    this.loadProjects();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  selectProject(projectId: string): void {
    if (!projectId || projectId === this.selectedProjectId()) {
      return;
    }
    this.selectedProjectId.set(projectId);
    this.evaluation.set(null);
    this.selectedEvaluationId.set('');
    this.results.set([]);
    this.stopPolling();
    this.resetMessages();
    this.loadProjectData(projectId);
  }

  modelsFor(providerId: string): { model_id: string; display_name: string }[] {
    return this.providers().find((provider) => provider.id === providerId)?.models ?? [];
  }

  addModelRow(): void {
    if (this.modelRows().length >= 5) {
      return;
    }
    this.modelRows.update((rows) => [
      ...rows,
      { provider: this.providers()[0]?.id ?? '', modelId: '' },
    ]);
  }

  removeModelRow(index: number): void {
    this.modelRows.update((rows) => rows.filter((_, position) => position !== index));
  }

  setRowProvider(index: number, providerId: string): void {
    this.modelRows.update((rows) =>
      rows.map((row, position) =>
        position === index ? { ...row, provider: providerId } : row,
      ),
    );
  }

  setRowModel(index: number, modelId: string): void {
    this.modelRows.update((rows) =>
      rows.map((row, position) =>
        position === index ? { ...row, modelId } : row,
      ),
    );
  }

  toggleMetric(key: string): void {
    this.selectedMetrics.update((keys) =>
      keys.includes(key) ? keys.filter((item) => item !== key) : [...keys, key],
    );
  }

  startEvaluation(): void {
    const projectId = this.selectedProjectId();
    const datasetId = this.datasetId();
    if (!projectId || !datasetId) {
      this.error.set('Choose a dataset before starting.');
      return;
    }
    if (!this.selectedMetrics().length) {
      this.error.set('Select at least one metric.');
      return;
    }
    const models = this.modelRows()
      .map((row) => ({ provider: row.provider, model_id: row.modelId.trim() }))
      .filter((row) => row.provider && row.model_id);
    if (!models.length) {
      this.error.set('Choose a provider and model id for at least one model.');
      return;
    }
    if (models.length !== this.modelRows().length) {
      this.error.set('Every model row needs a provider and model id.');
      return;
    }
    const keys = new Set(models.map((row) => `${row.provider}:${row.model_id}`));
    if (keys.size !== models.length) {
      this.error.set('Each selected model must be different.');
      return;
    }
    if (this.judgeRequired() && (!this.judgeProvider() || !this.judgeModel().trim())) {
      this.error.set('Choose the judge provider and model for DeepEval metrics.');
      return;
    }

    const parameters: Record<string, unknown> = {};
    const temperature = Number.parseFloat(this.temperature());
    if (!Number.isNaN(temperature)) {
      parameters['temperature'] = temperature;
    }
    const maxTokens = Number.parseInt(this.maxTokens(), 10);
    if (!Number.isNaN(maxTokens)) {
      parameters['max_tokens'] = maxTokens;
    }

    this.starting.set(true);
    this.resetMessages();
    this.evaluationService
      .create(projectId, {
        dataset: datasetId,
        metrics: this.selectedMetrics(),
        models,
        parameters,
        judge: this.judgeRequired()
          ? { provider: this.judgeProvider(), model_id: this.judgeModel().trim() }
          : null,
      })
      .subscribe({
        next: (created) => {
          this.starting.set(false);
          this.notice.set(
            created.status === 'failed'
              ? 'The run could not be started. See the error on the run.'
              : 'Evaluation queued. Results appear as cases finish.',
          );
          this.evaluations.update((rows) => [created, ...rows.filter((row) => row.id !== created.id)]);
          this.selectEvaluation(created.id);
        },
        error: (error: unknown) => {
          this.starting.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  selectEvaluation(evaluationId: string): void {
    this.selectedEvaluationId.set(evaluationId);
    this.expandedResultId.set(null);
    this.resultModelFilter.set('');
    this.resultStatusFilter.set('');
    this.stopPolling();
    this.loadEvaluation(evaluationId);
    this.loadResults(1);
  }

  rerun(evaluation: Evaluation): void {
    this.starting.set(true);
    this.resetMessages();
    this.evaluationService.rerun(evaluation.id).subscribe({
      next: (created) => {
        this.starting.set(false);
        this.notice.set('Rerun created as a new evaluation.');
        this.evaluations.update((rows) => [created, ...rows.filter((row) => row.id !== created.id)]);
        this.selectEvaluation(created.id);
      },
      error: (error: unknown) => {
        this.starting.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  setResultFilters(model: string, status: string): void {
    this.resultModelFilter.set(model);
    this.resultStatusFilter.set(status);
    this.loadResults(1);
  }

  toggleResult(rowId: string): void {
    this.expandedResultId.update((current) => (current === rowId ? null : rowId));
  }

  loadResults(page: number): void {
    const evaluationId = this.selectedEvaluationId();
    if (!evaluationId) {
      return;
    }
    this.resultLoading.set(true);
    this.evaluationService
      .results(evaluationId, {
        model: this.resultModelFilter() || undefined,
        status: this.resultStatusFilter() || undefined,
        page,
      })
      .subscribe({
        next: (pageResult: Paginated<EvaluationResultRow>) => {
          this.results.set(pageResult.results);
          this.resultCount.set(pageResult.count);
          this.resultPage.set(page);
          this.resultLoading.set(false);
        },
        error: (error: unknown) => {
          this.resultLoading.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  progress(evaluation: Evaluation): number {
    if (!evaluation.total_results) {
      return 0;
    }
    return Math.min(
      100,
      Math.round((evaluation.completed_cases / evaluation.total_results) * 100),
    );
  }

  resultPages(): number {
    return Math.max(1, Math.ceil(this.resultCount() / this.pageSize));
  }

  metricLabel(key: string): string {
    return this.metrics().find((metric) => metric.key === key)?.label ?? key;
  }

  average(model: EvaluationModel, metric: string): string {
    const value = model.summary?.metric_averages?.[metric];
    return typeof value === 'number' ? value.toFixed(2) : '—';
  }

  latency(model: EvaluationModel): string {
    const value = model.summary?.avg_latency_ms;
    if (value === undefined || value === null) {
      return '—';
    }
    return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
  }

  tokens(model: EvaluationModel): string {
    const input = model.summary?.total_input_tokens;
    const output = model.summary?.total_output_tokens;
    if (input === undefined && output === undefined) {
      return '—';
    }
    return `${input ?? '?'} in / ${output ?? '?'} out`;
  }

  statusClass(status: string): string {
    if (status === 'completed' || status === 'succeeded') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'running' || status === 'queued' || status === 'pending') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-rose-50 text-rose-700';
  }

  scoreClass(row: EvaluationResultRow, metric: string): string {
    const value = row.scores[metric];
    if (typeof value !== 'number') {
      return 'bg-slate-50 text-slate-500';
    }
    return value >= 0.5
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-amber-50 text-amber-700';
  }

  private loadMetrics(): void {
    this.evaluationService.metrics().subscribe({
      next: (response) => this.metrics.set(response.metrics),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private loadProjects(): void {
    this.loading.set(true);
    this.workspaceService.list().subscribe({
      next: (page) => {
        if (!page.results.length) {
          this.loading.set(false);
          return;
        }
        forkJoin(
          page.results.map((workspace) =>
            this.projectService.list(workspace.id).pipe(
              map((projects) =>
                projects.results.map((project) => ({
                  ...project,
                  workspaceName: workspace.name,
                })),
              ),
              catchError(() => of([] as ProjectOption[])),
            ),
          ),
        ).subscribe({
          next: (lists) => {
            const projects = lists.flat();
            this.projects.set(projects);
            this.loading.set(false);
            const first = projects[0];
            if (first) {
              this.selectedProjectId.set(first.id);
              this.loadProjectData(first.id);
            }
          },
          error: (error: unknown) => {
            this.loading.set(false);
            this.error.set(apiErrorMessage(error));
          },
        });
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadProjectData(projectId: string): void {
    forkJoin({
      datasets: this.datasetService.list(projectId).pipe(catchError(() => of([]))),
      providers: this.providerService.list(projectId).pipe(catchError(() => of([]))),
      evaluations: this.evaluationService.list(projectId).pipe(catchError(() => of([]))),
    }).subscribe({
      next: ({ datasets, providers, evaluations }) => {
        this.datasets.set(datasets);
        this.providers.set(providers);
        this.evaluations.set(evaluations);
        this.datasetId.set(datasets[0]?.id ?? '');
        const providerId = providers[0]?.id ?? '';
        this.modelRows.set([{ provider: providerId, modelId: providers[0]?.models[0]?.model_id ?? '' }]);
        this.judgeProvider.set(providerId);
        const first = evaluations[0];
        if (first) {
          this.selectEvaluation(first.id);
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private loadEvaluation(evaluationId: string): void {
    this.evaluationService.get(evaluationId).subscribe({
      next: (evaluation) => {
        this.evaluation.set(evaluation);
        this.evaluations.update((rows) =>
          rows.map((row) => (row.id === evaluation.id ? evaluation : row)),
        );
        if (evaluation.status === 'queued' || evaluation.status === 'running') {
          this.startPolling(evaluationId);
        } else {
          this.stopPolling();
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private startPolling(evaluationId: string): void {
    this.stopPolling();
    this.timer = setInterval(() => {
      this.evaluationService.get(evaluationId).subscribe({
        next: (evaluation) => {
          if (this.selectedEvaluationId() !== evaluationId) {
            return;
          }
          this.evaluation.set(evaluation);
          this.evaluations.update((rows) =>
            rows.map((row) => (row.id === evaluation.id ? evaluation : row)),
          );
          if (evaluation.status !== 'queued' && evaluation.status !== 'running') {
            this.stopPolling();
            this.loadResults(this.resultPage());
          }
        },
      });
    }, POLL_MS);
  }

  private stopPolling(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private resetMessages(): void {
    this.error.set(null);
    this.notice.set(null);
  }
}
