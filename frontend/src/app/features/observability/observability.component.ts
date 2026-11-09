import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  CostAmount,
  ObservabilityDashboard,
  ObservabilityFilters,
  ObservabilityService,
  TraceSummary,
  TrendPoint,
  UsageRow,
} from './observability.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

@Component({
  selector: 'msa-observability',
  standalone: true,
  imports: [DatePipe, RouterLink, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Observability</h1>
          <p class="msa-sub">
            Trace every model execution from the playground and evaluations.
            Inspect latency, tokens, errors and estimated costs.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
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
          <button
            type="button"
            class="msa-btn-secondary"
            [disabled]="loading()"
            (click)="refresh()"
          >
            <msa-icon name="refresh" [size]="15" /> Refresh
          </button>
        </div>
      </header>

      @if (error()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
          role="alert"
        >
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }

      @if (loading() && !summary()) {
        <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          @for (placeholder of [1, 2, 3, 4, 5]; track placeholder) {
            <div class="msa-card p-5">
              <div class="msa-skeleton h-3 w-20"></div>
              <div class="msa-skeleton mt-4 h-7 w-24"></div>
              <div class="msa-skeleton mt-2 h-3 w-32"></div>
            </div>
          }
        </div>
      } @else if (!projects().length) {
        <div class="msa-card mt-6 flex flex-col items-center p-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand">
            <msa-icon name="activity" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            Observability records are attached to model executions in a project.
            Create a project in Workspaces, then run a model or evaluation.
          </p>
        </div>
      } @else {
        @if (summary(); as data) {
        <section class="msa-card mt-5 p-4">
          <div class="flex flex-wrap items-end gap-3">
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">From</span>
              <input
                type="date"
                class="msa-input"
                [value]="fromDate()"
                (change)="setFilter('from', $any($event.target).value)"
              />
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">To</span>
              <input
                type="date"
                class="msa-input"
                [value]="toDate()"
                (change)="setFilter('to', $any($event.target).value)"
              />
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">Provider</span>
              <select
                class="msa-input min-w-[150px]"
                [value]="providerFilter()"
                (change)="setFilter('provider', $any($event.target).value)"
                aria-label="Filter by provider"
              >
                <option value="">All providers</option>
                @for (provider of data.facets.providers; track provider.id || provider.name) {
                  @if (provider.id) {
                    <option [value]="provider.id">{{ provider.name }}</option>
                  }
                }
              </select>
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">Model</span>
              <select
                class="msa-input min-w-[150px]"
                [value]="modelFilter()"
                (change)="setFilter('model', $any($event.target).value)"
                aria-label="Filter by model"
              >
                <option value="">All models</option>
                @for (model of data.facets.models; track model) {
                  <option [value]="model">{{ model }}</option>
                }
              </select>
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">Status</span>
              <select
                class="msa-input"
                [value]="statusFilter()"
                (change)="setFilter('status', $any($event.target).value)"
                aria-label="Filter by status"
              >
                <option value="">Any status</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
              </select>
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">Source</span>
              <select
                class="msa-input"
                [value]="sourceFilter()"
                (change)="setFilter('source', $any($event.target).value)"
                aria-label="Filter by source"
              >
                <option value="">All sources</option>
                <option value="playground">Playground</option>
                <option value="evaluation">Evaluations</option>
              </select>
            </label>
            <label class="text-xs text-muted">
              <span class="msa-label mb-1">Call type</span>
              <select
                class="msa-input"
                [value]="roleFilter()"
                (change)="setFilter('role', $any($event.target).value)"
                aria-label="Filter by call type"
              >
                <option value="">All calls</option>
                <option value="model">Model calls</option>
                <option value="judge">Judge calls</option>
              </select>
            </label>
            <button type="button" class="msa-btn-ghost mb-0.5" (click)="resetFilters()">
              <msa-icon name="close" [size]="13" /> Reset
            </button>
          </div>
          <p class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <span class="msa-badge bg-slate-50 text-slate-500">
              <msa-icon name="activity" [size]="11" />
              {{ data.telemetry.enabled ? 'OpenTelemetry active' : 'Database traces only' }}
            </span>
            @if (data.rollups?.through) {
              <span class="msa-badge bg-slate-50 text-slate-500">
                Rollups through {{ data.rollups?.through }}
              </span>
            }
            <span>{{ data.telemetry.detail }}</span>
          </p>
        </section>

        <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Total executions</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ data.totals.calls }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ data.totals.roles['model'] || 0 }} model ·
              {{ data.totals.roles['judge'] || 0 }} judge
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Succeeded / failed</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              <span class="text-emerald-600">{{ data.totals.succeeded }}</span>
              <span class="text-slate-300"> / </span>
              <span class="text-rose-600">{{ data.totals.failed }}</span>
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ failureRate(data) }} failure rate
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Average latency</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatDuration(data.totals.avg_latency_ms) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              Provider response time
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Tokens</p>
            <p class="mt-1 text-lg font-semibold tracking-tight text-ink">
              {{ formatTokens(data.totals.input_tokens, data.totals.output_tokens) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ data.totals.token_calls }} calls reported usage
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="flex items-center gap-1.5 text-xs font-medium text-muted">
              Estimated cost
              <span class="msa-badge" [class]="costBadgeClass(data.cost_status)">
                {{ data.cost_status }}
              </span>
            </p>
            <p class="mt-1 text-lg font-semibold tracking-tight text-ink">
              {{ costText(data.costs) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">{{ data.cost_detail }}</p>
          </article>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Execution trend</h2>
              <p class="text-xs text-muted">
                Calls per day, split by success and failure.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ data.trend.length }} day{{ data.trend.length === 1 ? '' : 's' }}
            </span>
          </div>

          @if (data.trend.length) {
            <div class="overflow-x-auto px-5 pb-4 pt-2">
              <div class="flex h-40 min-w-full items-end gap-1.5">
                @for (point of data.trend; track point.day) {
                  <div
                    class="group flex min-w-[14px] flex-1 flex-col items-center justify-end gap-1"
                    [attr.title]="trendTitle(point)"
                  >
                    <span class="text-[9px] text-slate-400 opacity-0 group-hover:opacity-100">
                      {{ point.count }}
                    </span>
                    <div
                      class="flex w-full flex-col justify-end overflow-hidden rounded-t bg-slate-100"
                      [style.height.%]="barHeight(point)"
                    >
                      <div
                        class="w-full bg-emerald-400"
                        [style.height.%]="successShare(point)"
                      ></div>
                      <div
                        class="w-full bg-rose-400"
                        [style.height.%]="failureShare(point)"
                      ></div>
                    </div>
                    <span class="whitespace-nowrap text-[9px] text-slate-400">
                      {{ point.day.slice(5) }}
                    </span>
                  </div>
                }
              </div>
            </div>
          } @else {
            <p class="px-5 py-10 text-center text-sm text-muted">
              No model calls match these filters.
            </p>
          }
        </section>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Model usage</h2>
                <p class="text-xs text-muted">Success, latency and usage by model.</p>
              </div>
            </div>
            @if (data.models.length) {
              <div class="overflow-x-auto">
                <table class="w-full text-left text-sm">
                  <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th class="px-5 py-2 font-semibold">Model</th>
                      <th class="px-3 py-2 text-right font-semibold">Calls</th>
                      <th class="px-3 py-2 text-right font-semibold">Failed</th>
                      <th class="px-3 py-2 text-right font-semibold">Avg</th>
                      <th class="px-3 py-2 text-right font-semibold">Tokens</th>
                      <th class="px-5 py-2 text-right font-semibold">Cost</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-line">
                    @for (row of data.models; track row.provider_id + row.provider_name + (row.model_id || '')) {
                      <tr>
                        <td class="px-5 py-3">
                          <p class="font-medium text-ink">{{ row.model_id }}</p>
                          <p class="text-[11px] text-slate-400">
                            {{ row.provider_name }} · {{ row.provider_kind }}
                            @if (row.roles['judge']) {
                              · {{ row.roles['judge'] }} judge
                            }
                          </p>
                        </td>
                        <td class="px-3 py-3 text-right text-slate-600">{{ row.count }}</td>
                        <td class="px-3 py-3 text-right">
                          <span
                            class="msa-badge"
                            [class]="row.failed ? 'bg-rose-50 text-rose-700' : 'bg-slate-50 text-slate-500'"
                          >
                            {{ row.failed }}
                          </span>
                        </td>
                        <td class="px-3 py-3 text-right text-slate-600">
                          {{ formatDuration(row.avg_latency_ms) }}
                        </td>
                        <td class="px-3 py-3 text-right text-[11px] text-slate-500">
                          {{ formatTokens(row.input_tokens, row.output_tokens) }}
                        </td>
                        <td class="px-5 py-3 text-right text-[11px] text-slate-500">
                          {{ costText(row.costs) }}
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">No calls yet.</p>
            }
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Provider usage</h2>
                <p class="text-xs text-muted">Which providers are serving calls.</p>
              </div>
            </div>
            @if (data.providers.length) {
              <ul class="divide-y divide-line">
                @for (row of data.providers; track row.provider_id + row.provider_name) {
                  <li class="flex items-center gap-3 px-5 py-3">
                    <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
                      <msa-icon name="plug" [size]="15" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-sm font-medium text-ink">
                        {{ row.provider_name }}
                      </span>
                      <span class="block text-[11px] text-slate-400">
                        {{ row.count }} calls · {{ row.failed }} failed ·
                        {{ formatDuration(row.avg_latency_ms) }} avg
                      </span>
                    </span>
                    <span class="text-right text-[11px] text-slate-500">
                      {{ formatTokens(row.input_tokens, row.output_tokens) }}
                      <span class="mt-1 block">{{ costText(row.costs) }}</span>
                    </span>
                  </li>
                }
              </ul>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">No calls yet.</p>
            }
          </section>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Error categories</h2>
                <p class="text-xs text-muted">Failed calls grouped by cause.</p>
              </div>
            </div>
            @if (data.errors.length) {
              <ul class="divide-y divide-line">
                @for (item of data.errors; track item.category) {
                  <li class="flex items-center gap-3 px-5 py-3">
                    <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
                      <msa-icon name="alert" [size]="14" />
                    </span>
                    <span class="min-w-0 flex-1 font-mono text-xs text-slate-600">
                      {{ item.category }}
                    </span>
                    <span class="msa-badge bg-rose-50 text-rose-700">{{ item.count }}</span>
                  </li>
                }
              </ul>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">
                No failed calls in this range.
              </p>
            }
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Slowest calls</h2>
                <p class="text-xs text-muted">Investigate long-running executions.</p>
              </div>
            </div>
            @if (data.slowest.length) {
              <ul class="divide-y divide-line">
                @for (trace of data.slowest; track trace.id) {
                  <li>
                    <a
                      class="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-canvas/60"
                      [routerLink]="['/observability/traces', trace.id]"
                    >
                      <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                        <msa-icon name="clock" [size]="14" />
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium text-ink">
                          {{ trace.model_id }} · {{ trace.request_preview }}
                        </span>
                        <span class="block text-[11px] text-slate-400">
                          {{ trace.source_label }} · {{ trace.started_at | date: 'medium' }}
                        </span>
                      </span>
                      <span class="text-xs font-medium text-slate-600">
                        {{ formatDuration(trace.duration_ms) }}
                      </span>
                    </a>
                  </li>
                }
              </ul>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">
                No timed calls yet.
              </p>
            }
          </section>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Recent traces</h2>
              <p class="text-xs text-muted">
                One row per model or judge call. Open a trace to inspect its spans.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ tracePage()?.count ?? 0 }}
            </span>
          </div>

          @if (tracePage()?.results?.length) {
            <ul class="divide-y divide-line">
              @for (trace of tracePage()!.results; track trace.id) {
                <li>
                  <a
                    class="flex flex-wrap items-center gap-3 px-5 py-3 transition-colors hover:bg-canvas/60"
                    [routerLink]="['/observability/traces', trace.id]"
                  >
                    <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-slate-400 ring-1 ring-line">
                      <msa-icon [name]="trace.role === 'judge' ? 'sparkles' : 'activity'" [size]="14" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-sm font-medium text-ink">
                        {{ trace.request_preview || 'No preview available' }}
                      </span>
                      <span class="block truncate text-[11px] text-slate-400">
                        {{ trace.provider_name }} · {{ trace.model_id }} ·
                        {{ trace.source_label }} · {{ trace.started_at | date: 'medium' }}
                      </span>
                    </span>
                    <span class="msa-badge bg-slate-50 capitalize text-slate-500">
                      {{ trace.role }}
                    </span>
                    <span class="msa-badge" [class]="statusClass(trace.status)">
                      {{ trace.status }}
                    </span>
                    <span class="w-16 text-right text-[11px] text-slate-500">
                      {{ formatDuration(trace.duration_ms) }}
                    </span>
                    <span class="w-24 text-right text-[11px] text-slate-500">
                      {{ formatTokens(trace.input_tokens, trace.output_tokens) }}
                    </span>
                  </a>
                </li>
              }
            </ul>
            <div class="flex items-center justify-between border-t border-line px-5 py-3">
              <span class="text-[11px] text-slate-400">
                Page {{ tracePageNumber() }} of
                {{ totalPages() }}
              </span>
              <div class="flex gap-2">
                <button
                  type="button"
                  class="msa-btn-ghost"
                  [disabled]="!tracePage()?.previous || loading()"
                  (click)="goToPage(tracePageNumber() - 1)"
                >
                  Previous
                </button>
                <button
                  type="button"
                  class="msa-btn-ghost"
                  [disabled]="!tracePage()?.next || loading()"
                  (click)="goToPage(tracePageNumber() + 1)"
                >
                  Next
                </button>
              </div>
            </div>
          } @else {
            <div class="p-10 text-center">
              <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-400">
                <msa-icon name="activity" [size]="22" />
              </span>
              <p class="mt-3 text-sm font-medium text-ink">No traces yet</p>
              <p class="mt-1 text-xs text-muted">
                Run a model in the Playground or start an evaluation. Every call
                will appear here.
              </p>
            </div>
          }
        </section>
        }
      }
    </div>
  `,
})
export class ObservabilityComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly observability = inject(ObservabilityService);

  readonly workspaces = signal<Workspace[]>([]);
  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly summary = signal<ObservabilityDashboard | null>(null);
  readonly tracePage = signal<Paginated<TraceSummary> | null>(null);
  readonly tracePageNumber = signal(1);

  readonly fromDate = signal('');
  readonly toDate = signal('');
  readonly providerFilter = signal('');
  readonly modelFilter = signal('');
  readonly statusFilter = signal('');
  readonly sourceFilter = signal('');
  readonly roleFilter = signal('');

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly totalPages = computed(() => {
    const page = this.tracePage();
    if (!page) {
      return 1;
    }
    return Math.max(1, Math.ceil(page.count / 50));
  });

  ngOnInit(): void {
    this.loadProjects();
  }

  selectProject(projectId: string): void {
    if (!projectId || projectId === this.selectedProjectId()) {
      return;
    }
    this.selectedProjectId.set(projectId);
    this.resetFilters(false);
    this.loadData();
  }

  setFilter(key: keyof ObservabilityFilters, value: string): void {
    const setters: Record<keyof ObservabilityFilters, (value: string) => void> = {
      from: (next) => this.fromDate.set(next),
      to: (next) => this.toDate.set(next),
      provider: (next) => this.providerFilter.set(next),
      model: (next) => this.modelFilter.set(next),
      status: (next) => this.statusFilter.set(next),
      source: (next) => this.sourceFilter.set(next),
      role: (next) => this.roleFilter.set(next),
    };
    setters[key](value);
    this.tracePageNumber.set(1);
    this.loadData();
  }

  resetFilters(reload = true): void {
    this.fromDate.set('');
    this.toDate.set('');
    this.providerFilter.set('');
    this.modelFilter.set('');
    this.statusFilter.set('');
    this.sourceFilter.set('');
    this.roleFilter.set('');
    this.tracePageNumber.set(1);
    if (reload) {
      this.loadData();
    }
  }

  refresh(): void {
    this.loadData();
  }

  goToPage(page: number): void {
    if (page < 1) {
      return;
    }
    this.tracePageNumber.set(page);
    this.loadTraces();
  }

  formatDuration(value: number | null): string {
    if (value === null) {
      return 'Unavailable';
    }
    return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
  }

  formatTokens(input: number | null, output: number | null): string {
    if (input === null && output === null) {
      return 'Unavailable';
    }
    return `${input ?? '?'} in / ${output ?? '?'} out`;
  }

  costText(costs: CostAmount[]): string {
    if (!costs.length) {
      return 'Unavailable';
    }
    return costs.map((cost) => `${cost.amount} ${cost.currency}`).join(' · ');
  }

  costBadgeClass(status: string): string {
    if (status === 'estimated') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'partial') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-slate-50 text-slate-500';
  }

  statusClass(status: string): string {
    return status === 'succeeded'
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-rose-50 text-rose-700';
  }

  failureRate(data: ObservabilityDashboard): string {
    if (!data.totals.calls) {
      return '0%';
    }
    return `${Math.round((data.totals.failed / data.totals.calls) * 100)}%`;
  }

  barHeight(point: TrendPoint): number {
    const max = Math.max(...(this.summary()?.trend ?? []).map((item) => item.count), 1);
    return Math.max((point.count / max) * 100, point.count ? 4 : 0);
  }

  successShare(point: TrendPoint): number {
    return point.count ? (point.succeeded / point.count) * 100 : 0;
  }

  failureShare(point: TrendPoint): number {
    return point.count ? (point.failed / point.count) * 100 : 0;
  }

  trendTitle(point: TrendPoint): string {
    return `${point.day}: ${point.count} calls · ${point.succeeded} succeeded · ${point.failed} failed`;
  }

  private loadProjects(): void {
    this.loading.set(true);
    this.error.set(null);
    this.workspaceService.list().subscribe({
      next: (page) => {
        this.workspaces.set(page.results);
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
              this.loadData();
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

  private filters(): ObservabilityFilters {
    return {
      from: this.fromDate(),
      to: this.toDate(),
      provider: this.providerFilter(),
      model: this.modelFilter(),
      status: this.statusFilter(),
      source: this.sourceFilter(),
      role: this.roleFilter(),
    };
  }

  private loadData(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      summary: this.observability.dashboard(projectId, this.filters()),
      traces: this.observability.traces(projectId, this.filters(), this.tracePageNumber()),
    }).subscribe({
      next: ({ summary, traces }) => {
        this.summary.set(summary);
        this.tracePage.set(traces);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadTraces(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loading.set(true);
    this.observability
      .traces(projectId, this.filters(), this.tracePageNumber())
      .subscribe({
        next: (page) => {
          this.tracePage.set(page);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }
}
