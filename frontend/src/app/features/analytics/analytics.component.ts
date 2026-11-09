import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  AnalyticsCost,
  AnalyticsDashboard,
  AnalyticsFilters,
  AnalyticsReportDetail,
  AnalyticsReportInput,
  AnalyticsReportSummary,
  AnalyticsService,
  AnalyticsTrendPoint,
  ModelPerformance,
  ModelPerformanceResponse,
  ModelTrendPoint,
  REPORT_SECTIONS,
  ReportSectionKey,
} from './analytics.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

const ALL_SECTIONS = REPORT_SECTIONS.map((section) => section.key);
const TONES = {
  brand: 'bg-brand-soft text-brand',
  emerald: 'bg-emerald-50 text-emerald-600',
  violet: 'bg-violet-soft text-violet',
  amber: 'bg-amber-50 text-amber-600',
  rose: 'bg-rose-50 text-rose-600',
} as const;

@Component({
  selector: 'msa-analytics',
  standalone: true,
  imports: [IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Analytics</h1>
          <p class="msa-sub">
            Usage, performance, costs, evaluation history and security activity
            from your project's actual records.
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
      @if (notice()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700"
          role="status"
        >
          <msa-icon name="check-circle" [size]="16" />
          <span>{{ notice() }}</span>
        </p>
      }

      @if (loading() && !data()) {
        <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          @for (placeholder of [1, 2, 3, 4, 5, 6, 7, 8]; track placeholder) {
            <div class="msa-card p-5">
              <div class="msa-skeleton h-3 w-24"></div>
              <div class="msa-skeleton mt-4 h-7 w-28"></div>
              <div class="msa-skeleton mt-2 h-3 w-36"></div>
            </div>
          }
        </div>
      } @else if (!projects().length) {
        <div class="msa-card mt-6 flex flex-col items-center p-12 text-center">
          <span
            class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand"
          >
            <msa-icon name="chart" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            Analytics uses the executions, evaluations and security scans
            attached to a project. Create one in Workspaces, then run a model or
            evaluation.
          </p>
        </div>
      } @else {
        @if (data(); as d) {
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
                class="msa-input min-w-[160px]"
                [value]="providerFilter()"
                (change)="setFilter('provider', $any($event.target).value)"
                aria-label="Filter by provider"
              >
                <option value="">All providers</option>
                @for (provider of d.facets.providers; track provider.id || provider.name) {
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
                @for (model of d.facets.models; track model) {
                  <option [value]="model">{{ model }}</option>
                }
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
            <button type="button" class="msa-btn-ghost mb-0.5" (click)="resetFilters()">
              <msa-icon name="close" [size]="13" /> Reset
            </button>
          </div>
          <p class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ d.range.from }} → {{ d.range.to }} · {{ d.range.days }} days
            </span>
            <span class="msa-badge bg-slate-50 text-slate-500">
              <msa-icon name="clock" [size]="11" /> Timezone {{ d.range.timezone }}
            </span>
            @if (d.rollups.through) {
              <span class="msa-badge bg-slate-50 text-slate-500">
                Rollups through {{ d.rollups.through }}
              </span>
            }
            @if (d.filters.provider_name) {
              <span class="msa-badge bg-brand-soft text-brand">
                {{ d.filters.provider_name }}
              </span>
            }
            @if (d.filters.model) {
              <span class="msa-badge bg-brand-soft text-brand">{{ d.filters.model }}</span>
            }
            <span>Figures come from stored executions, traces, evaluations and findings.</span>
          </p>
        </section>

        <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <article class="msa-card p-5">
            <div class="flex items-start justify-between">
              <span [class]="'msa-tile ' + tones.brand">
                <msa-icon name="activity" [size]="17" />
              </span>
              <span class="msa-badge bg-slate-50 text-slate-500">model calls</span>
            </div>
            <p class="mt-4 text-xs font-medium text-muted">Model calls</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatNumber(d.summary.model_calls.total) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ formatNumber(d.summary.model_calls.succeeded) }} succeeded ·
              {{ formatNumber(d.summary.model_calls.failed) }} failed ·
              {{ percent(d.summary.model_calls.failure_rate) }} failure rate
            </p>
          </article>

          <article class="msa-card p-5">
            <div class="flex items-start justify-between">
              <span [class]="'msa-tile ' + tones.emerald">
                <msa-icon name="play" [size]="17" />
              </span>
              <span class="msa-badge bg-slate-50 text-slate-500">playground</span>
            </div>
            <p class="mt-4 text-xs font-medium text-muted">Playground executions</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatNumber(d.summary.executions.total) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ formatNumber(d.summary.executions.succeeded) }} succeeded ·
              {{ formatNumber(d.summary.executions.partial) }} partial ·
              {{ formatNumber(d.summary.executions.failed) }} failed
            </p>
          </article>

          <article class="msa-card p-5">
            <div class="flex items-start justify-between">
              <span [class]="'msa-tile ' + tones.violet">
                <msa-icon name="database" [size]="17" />
              </span>
              <span class="msa-badge bg-slate-50 text-slate-500">tokens</span>
            </div>
            <p class="mt-4 text-xs font-medium text-muted">Token consumption</p>
            <p class="mt-1 text-lg font-semibold tracking-tight text-ink">
              {{ tokens(d.summary.model_calls.input_tokens, d.summary.model_calls.output_tokens) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ formatNumber(d.summary.model_calls.token_calls) }} calls reported usage ·
              {{ formatNumber(d.summary.model_calls.calls_without_tokens) }} missing
            </p>
          </article>

          <article class="msa-card p-5">
            <div class="flex items-start justify-between">
              <span [class]="'msa-tile ' + tones.amber">
                <msa-icon name="clock" [size]="17" />
              </span>
              <span class="msa-badge bg-slate-50 text-slate-500">latency</span>
            </div>
            <p class="mt-4 text-xs font-medium text-muted">Average response time</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ duration(d.summary.model_calls.avg_latency_ms) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              Provider response time; full duration
              {{ duration(d.summary.model_calls.avg_duration_ms) }}
            </p>
          </article>

          <article class="msa-card p-5">
            <p class="flex items-center gap-1.5 text-xs font-medium text-muted">
              Estimated cost
              <span class="msa-badge" [class]="costBadge(d.cost.status)">
                {{ d.cost.status }}
              </span>
            </p>
            <p class="mt-1 text-lg font-semibold tracking-tight text-ink">
              {{ costs(d.cost.currencies) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">{{ d.cost.detail }}</p>
          </article>

          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Evaluation runs</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatNumber(d.summary.evaluations.total) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ formatNumber(d.summary.evaluations.completed) }} completed ·
              {{ formatNumber(d.summary.evaluations.failed) }} failed ·
              mean score {{ score(d.summary.evaluations.avg_score) }}
            </p>
          </article>

          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Security activity</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatNumber(d.summary.security.scans) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              scans · {{ formatNumber(d.summary.security.findings) }} findings ·
              {{ formatNumber(d.summary.security.open_findings) }} open
            </p>
          </article>

          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Data quality</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {{ formatNumber(d.data_quality.model_calls_without_tokens) }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">
              calls without token data ·
              {{ formatNumber(d.data_quality.calls_without_cost_estimate) }} without
              a cost estimate
            </p>
          </article>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-[1.5fr_1fr]">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Usage and performance trend</h2>
                <p class="text-xs text-muted">
                  Daily model calls, failures, token usage and evaluation activity.
                </p>
              </div>
              <span class="msa-badge bg-slate-50 text-slate-500">
                {{ d.trend.length }} day{{ d.trend.length === 1 ? '' : 's' }}
              </span>
            </div>
            @if (d.trend.length) {
              <div class="overflow-x-auto px-5 pb-4 pt-2">
                <div class="flex h-44 min-w-full items-end gap-1.5">
                  @for (point of d.trend; track point.day) {
                    <div
                      class="group flex min-w-[14px] flex-1 flex-col items-center justify-end gap-1"
                      [attr.title]="trendTitle(point)"
                    >
                      <span class="text-[9px] text-slate-400 opacity-0 group-hover:opacity-100">
                        {{ point.calls }}
                      </span>
                      <div
                        class="flex w-full flex-col justify-end overflow-hidden rounded-t bg-slate-100"
                        [style.height.%]="trendBarHeight(point)"
                      >
                        <div
                          class="w-full bg-emerald-400"
                          [style.height.%]="trendSuccessShare(point)"
                        ></div>
                        <div
                          class="w-full bg-rose-400"
                          [style.height.%]="trendFailureShare(point)"
                        ></div>
                      </div>
                      <span class="whitespace-nowrap text-[9px] text-slate-400">
                        {{ point.day.slice(5) }}
                      </span>
                    </div>
                  }
                </div>
              </div>
              <div class="grid grid-cols-3 gap-2 border-t border-line px-5 py-3 text-center">
                <div>
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Calls</p>
                  <p class="text-sm font-semibold text-ink">{{ formatNumber(totalCalls()) }}</p>
                </div>
                <div>
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Evaluations</p>
                  <p class="text-sm font-semibold text-ink">{{ formatNumber(totalEvaluations()) }}</p>
                </div>
                <div>
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Security findings</p>
                  <p class="text-sm font-semibold text-ink">{{ formatNumber(totalSecurityFindings()) }}</p>
                </div>
              </div>
            } @else {
              <p class="px-5 py-10 text-center text-sm text-muted">
                No activity matches these filters.
              </p>
            }
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Cost breakdown</h2>
                <p class="text-xs text-muted">Only configured, provider-reported usage is priced.</p>
              </div>
              <span class="msa-badge" [class]="costBadge(d.cost.status)">{{ d.cost.status }}</span>
            </div>
            <div class="space-y-3 p-5">
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-muted">Estimated total</span>
                <span class="text-sm font-semibold text-ink">{{ costs(d.cost.currencies) }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-muted">Estimated calls</span>
                <span class="text-sm font-medium text-ink">{{ formatNumber(d.cost.estimated_calls) }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-muted">Unpriced calls</span>
                <span class="text-sm font-medium text-ink">{{ formatNumber(d.cost.unavailable_calls) }}</span>
              </div>
              <p class="rounded-lg bg-canvas p-3 text-[11px] leading-relaxed text-slate-500">
                {{ d.cost.note }}
              </p>
              @for (provider of d.cost.by_provider; track provider.provider_name + provider.provider_kind) {
                <div class="flex items-start justify-between gap-3 border-t border-line pt-3">
                  <span class="min-w-0">
                    <span class="block truncate text-xs font-medium text-ink">
                      {{ provider.provider_name }}
                    </span>
                    <span class="block text-[10px] text-slate-400">
                      {{ provider.provider_kind }} · {{ formatNumber(provider.estimated_calls) }} estimated calls
                    </span>
                  </span>
                  <span class="text-right text-[11px] text-slate-500">{{ costs(provider.costs) }}</span>
                </div>
              }
            </div>
          </section>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Model usage</h2>
              <p class="text-xs text-muted">
                Calls, latency, tokens, cost estimates and stored evaluation scores by model.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ d.usage.models.length }} model{{ d.usage.models.length === 1 ? '' : 's' }}
            </span>
          </div>
          @if (d.usage.models.length) {
            <div class="overflow-x-auto">
              <table class="msa-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Calls</th>
                    <th>Failed</th>
                    <th>Avg latency</th>
                    <th>Tokens</th>
                    <th>Cost</th>
                    <th>Eval score</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of d.usage.models; track row.provider_id + row.provider_name + row.model_id) {
                    <tr>
                      <td>
                        <p class="text-sm font-medium text-ink">{{ row.model_id }}</p>
                        <p class="text-[11px] text-slate-400">
                          {{ row.provider_name }} · {{ row.provider_kind }}
                        </p>
                      </td>
                      <td class="text-xs text-slate-600">{{ formatNumber(row.count) }}</td>
                      <td>
                        <span
                          class="msa-badge"
                          [class]="row.failed ? 'bg-rose-50 text-rose-700' : 'bg-slate-50 text-slate-500'"
                        >
                          {{ formatNumber(row.failed) }}
                        </span>
                      </td>
                      <td class="text-xs text-slate-600">{{ duration(row.avg_latency_ms) }}</td>
                      <td class="text-[11px] text-slate-500">{{ tokens(row.input_tokens, row.output_tokens) }}</td>
                      <td class="text-[11px] text-slate-500">{{ costs(row.costs) }}</td>
                      <td class="text-xs text-slate-600">{{ score(row.evaluation?.avg_score) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <p class="px-5 py-8 text-center text-sm text-muted">No model calls in this period.</p>
          }
          <div class="border-t border-line px-5 py-3 text-[11px] text-slate-400">
            Provider filter: {{ d.filters.provider_name || 'all providers' }} ·
            Model filter: {{ d.filters.model || 'all models' }} ·
            Source: {{ sourceLabel(d.filters.source) }}
          </div>
        </section>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Compare model performance</h2>
              <p class="text-xs text-muted">
                Select two models to compare historical calls, latency, tokens, cost and evaluation scores.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ modelsForComparison().length }} available
            </span>
          </div>
          @if (modelsForComparison().length) {
            <div class="flex flex-wrap items-end gap-3 px-5 pt-4">
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Model A</span>
                <select
                  class="msa-input min-w-[210px]"
                  [value]="compareA()"
                  (change)="compareA.set($any($event.target).value)"
                  aria-label="First comparison model"
                >
                  @for (model of modelsForComparison(); track model.key) {
                    <option [value]="model.key" [selected]="compareA() === model.key">
                      {{ modelLabel(model) }}
                    </option>
                  }
                </select>
              </label>
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Model B</span>
                <select
                  class="msa-input min-w-[210px]"
                  [value]="compareB()"
                  (change)="compareB.set($any($event.target).value)"
                  aria-label="Second comparison model"
                >
                  <option value="" [selected]="!compareB()">Choose a model</option>
                  @for (model of modelsForComparison(); track model.key) {
                    <option [value]="model.key" [selected]="compareB() === model.key">
                      {{ modelLabel(model) }}
                    </option>
                  }
                </select>
              </label>
              <p class="pb-1 text-[11px] text-slate-400">
                Historical points use the same date range. Scores are stored evaluation averages.
              </p>
            </div>
          }
          @if (compareModels().length) {
            <div class="grid gap-4 p-5 xl:grid-cols-2">
              @for (model of compareModels(); track model.key) {
                <article class="rounded-xl border border-line p-4">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <p class="truncate text-sm font-semibold text-ink">{{ model.model_id }}</p>
                      <p class="text-[11px] text-slate-400">{{ model.provider_name }} · {{ model.provider_kind }}</p>
                    </div>
                    <span class="msa-badge" [class]="costBadge(model.cost_status)">{{ model.cost_status }}</span>
                  </div>
                  <div class="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                    <span>{{ formatNumber(model.calls) }} calls</span>
                    <span>{{ percent(model.failure_rate) }} failure rate</span>
                    <span>{{ duration(model.avg_latency_ms) }} avg latency</span>
                    <span>Score {{ score(model.evaluation.avg_score) }}</span>
                    <span>{{ tokens(model.input_tokens, model.output_tokens) }}</span>
                    <span>{{ costs(model.costs) }}</span>
                  </div>
                  <div class="mt-4 flex h-24 items-end gap-1">
                    @for (point of model.trend; track point.day) {
                      <div
                        class="flex h-full flex-1 flex-col justify-end rounded-t bg-slate-100"
                        [attr.title]="modelTrendTitle(point)"
                      >
                        <div
                          class="w-full rounded-t bg-brand"
                          [style.height.%]="modelBarHeight(point)"
                        ></div>
                      </div>
                    }
                  </div>
                  <div class="mt-2 flex justify-between text-[10px] text-slate-400">
                    <span>{{ model.trend.length ? model.trend[0].day : '' }}</span>
                    <span>{{ model.trend.length ? model.trend[model.trend.length - 1].day : '' }}</span>
                  </div>
                </article>
              }
            </div>
          } @else {
            <p class="px-5 py-8 text-center text-sm text-muted">
              Choose at least one model with calls or evaluation scores in this period.
            </p>
          }
          <p class="border-t border-line px-5 py-3 text-[11px] text-slate-400">
            {{ modelData()?.comparison_note }}
          </p>
        </section>

        <div class="mt-4 grid gap-4 xl:grid-cols-[1.5fr_1fr]">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Evaluation history</h2>
                <p class="text-xs text-muted">
                  Stored runs and their available metric averages.
                </p>
              </div>
              <span class="msa-badge bg-slate-50 text-slate-500">
                {{ d.evaluation_history.length }}
              </span>
            </div>
            @if (d.evaluation_history.length) {
              <div class="overflow-x-auto">
                <table class="msa-table">
                  <thead>
                    <tr>
                      <th>Dataset</th>
                      <th>Status</th>
                      <th>Score</th>
                      <th>Models</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (run of d.evaluation_history; track run.id) {
                      <tr>
                        <td>
                          <p class="text-sm font-medium text-ink">{{ run.dataset_name }}</p>
                          <p class="text-[11px] text-slate-400">
                            v{{ run.dataset_version }} · {{ run.total_cases }} cases
                          </p>
                        </td>
                        <td>
                          <span class="msa-badge" [class]="statusBadge(run.status)">
                            {{ run.status }}
                          </span>
                        </td>
                        <td class="text-xs font-medium text-ink">{{ score(run.avg_score) }}</td>
                        <td class="max-w-[230px] text-[11px] text-slate-500">
                          @for (model of run.models; track model.id) {
                            <span class="block truncate">
                              {{ model.model_id }} · {{ score(model.avg_score) }}
                            </span>
                          }
                        </td>
                        <td class="text-[11px] text-slate-400">{{ run.created_at.slice(0, 16) }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">
                No evaluation runs in this period.
              </p>
            }
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Security activity</h2>
                <p class="text-xs text-muted">Scans and findings detected in this period.</p>
              </div>
              <span class="msa-badge bg-slate-50 text-slate-500">
                {{ formatNumber(d.summary.security.findings) }} findings
              </span>
            </div>
            <div class="p-5">
              <div class="grid grid-cols-2 gap-2 text-xs">
                <div class="rounded-lg bg-canvas p-3">
                  <p class="text-slate-400">Scans</p>
                  <p class="mt-1 text-lg font-semibold text-ink">{{ formatNumber(d.summary.security.scans) }}</p>
                </div>
                <div class="rounded-lg bg-canvas p-3">
                  <p class="text-slate-400">Open findings</p>
                  <p class="mt-1 text-lg font-semibold text-ink">{{ formatNumber(d.summary.security.open_findings) }}</p>
                </div>
              </div>
              <div class="mt-4 space-y-2">
                @for (item of severityRows(); track item.key) {
                  <div class="flex items-center gap-2">
                    <span class="w-16 text-[11px] capitalize text-slate-500">{{ item.key }}</span>
                    <div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div class="h-full rounded-full" [class]="severityBar(item.key)" [style.width.%]="severityPercent(item.count)"></div>
                    </div>
                    <span class="w-6 text-right text-[11px] text-slate-500">{{ item.count }}</span>
                  </div>
                }
              </div>
              @if (d.summary.security.recent_scans.length) {
                <div class="mt-4 border-t border-line pt-3">
                  <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Recent scans</p>
                  @for (scan of d.summary.security.recent_scans; track scan.id) {
                    <div class="flex items-start justify-between gap-2 py-1.5">
                      <span class="min-w-0">
                        <span class="block truncate text-[11px] text-ink">{{ scan.target_label }}</span>
                        <span class="block text-[10px] text-slate-400">{{ scan.target_type }} · {{ scan.created_at.slice(0, 16) }}</span>
                      </span>
                      <span class="msa-badge" [class]="statusBadge(scan.status)">{{ scan.status }}</span>
                    </div>
                  }
                </div>
              }
              <p class="mt-3 rounded-lg bg-canvas p-2 text-[10px] leading-relaxed text-slate-500">
                {{ d.summary.security.note }}
              </p>
            </div>
          </section>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Reports</h2>
              <p class="text-xs text-muted">
                Generate a reproducible snapshot and export it as PDF or CSV.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ reports().length }} saved
            </span>
          </div>
          <div class="grid gap-4 p-5 xl:grid-cols-[360px_1fr]">
            <div class="space-y-3">
              <label class="block text-xs text-muted">
                <span class="msa-label mb-1">Report title</span>
                <input
                  class="msa-input"
                  placeholder="Optional: Analytics report"
                  [value]="reportTitle()"
                  (input)="reportTitle.set($any($event.target).value)"
                />
              </label>
              <div>
                <p class="msa-label">Include sections</p>
                <div class="mt-1 grid grid-cols-2 gap-1.5">
                  @for (section of reportSections; track section.key) {
                    <label class="flex cursor-pointer items-center gap-2 rounded-lg border border-line px-2 py-1.5 text-[11px] text-slate-600 hover:bg-canvas/60">
                      <input
                        type="checkbox"
                        [checked]="selectedSections().includes(section.key)"
                        (change)="toggleSection(section.key)"
                      />
                      {{ section.label }}
                    </label>
                  }
                </div>
              </div>
              <button
                type="button"
                class="msa-btn-primary w-full justify-center"
                [disabled]="generating() || !selectedSections().length"
                (click)="generateReport()"
              >
                <msa-icon [name]="generating() ? 'refresh' : 'plus'" [size]="15" />
                {{ generating() ? 'Generating…' : 'Generate report' }}
              </button>
              <p class="rounded-lg bg-canvas p-3 text-[11px] leading-relaxed text-slate-500">
                The report stores the period, filters and figures at generation time.
                Later data will not silently change it.
              </p>
            </div>

            <div class="space-y-3">
              @if (reports().length) {
                <div class="max-h-56 divide-y divide-line overflow-y-auto rounded-xl border border-line">
                  @for (report of reports(); track report.id) {
                    <button
                      type="button"
                      class="flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-canvas/60"
                      [class]="selectedReport()?.id === report.id ? 'bg-brand-soft/40' : ''"
                      (click)="selectReport(report.id)"
                    >
                      <span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                        <msa-icon name="chart" [size]="13" />
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-xs font-medium text-ink">{{ report.title }}</span>
                        <span class="block text-[10px] text-slate-400">
                          {{ report.period_from }} → {{ report.period_to }} ·
                          {{ report.section_labels.join(', ') }}
                        </span>
                      </span>
                      <msa-icon name="arrow-right" [size]="13" class="mt-1 text-slate-400" />
                    </button>
                  }
                </div>
              } @else {
                <p class="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">
                  No reports yet. Choose sections and generate one.
                </p>
              }

              @if (selectedReport(); as report) {
                <div class="rounded-xl border border-line p-4">
                  <div class="flex flex-wrap items-start justify-between gap-2">
                    <div class="min-w-0">
                      <p class="text-sm font-semibold text-ink">{{ report.title }}</p>
                      <p class="text-[11px] text-slate-400">
                        {{ report.period_from }} → {{ report.period_to }} · generated
                        {{ report.created_at.slice(0, 16) }} by
                        {{ report.created_by_email || 'unknown user' }}
                      </p>
                    </div>
                    <div class="flex gap-2">
                      <button type="button" class="msa-btn-secondary" (click)="downloadReport('csv')">
                        <msa-icon name="database" [size]="13" /> CSV
                      </button>
                      <button type="button" class="msa-btn-secondary" (click)="downloadReport('pdf')">
                        <msa-icon name="upload" [size]="13" /> PDF
                      </button>
                    </div>
                  </div>
                  <div class="mt-3 max-h-64 space-y-3 overflow-y-auto rounded-lg bg-canvas p-3">
                    @for (section of report.document.sections; track section.key) {
                      <div>
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{{ section.title }}</p>
                        @for (row of section.rows; track $index) {
                          <p class="mt-1 text-[11px] leading-relaxed text-slate-600">
                            <span class="font-medium text-slate-700">{{ row[0] }}:</span> {{ row[1] }}
                          </p>
                        }
                      </div>
                    }
                  </div>
                  <div class="mt-3 text-[10px] leading-relaxed text-slate-400">
                    Stored snapshot. Exports use the figures above, not a fresh query.
                  </div>
                </div>
              }
            </div>
          </div>
        </section>

        <section class="msa-card mt-4 p-5">
          <h2 class="msa-section-title">What these figures mean</h2>
          <ul class="mt-2 space-y-1.5 text-[11px] leading-relaxed text-slate-500">
            @for (note of d.limitations; track $index) {
              <li class="flex gap-2">
                <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300"></span>
                <span>{{ note }}</span>
              </li>
            }
          </ul>
        </section>
        }
      }
    </div>
  `,
})
export class AnalyticsComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly analyticsService = inject(AnalyticsService);

  readonly reportSections = REPORT_SECTIONS;
  readonly tones = TONES;

  readonly workspaces = signal<Workspace[]>([]);
  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly data = signal<AnalyticsDashboard | null>(null);
  readonly modelData = signal<ModelPerformanceResponse | null>(null);
  readonly reports = signal<AnalyticsReportSummary[]>([]);
  readonly selectedReport = signal<AnalyticsReportDetail | null>(null);
  readonly reportTitle = signal('');
  readonly selectedSections = signal<ReportSectionKey[]>([...ALL_SECTIONS]);
  readonly compareA = signal('');
  readonly compareB = signal('');

  readonly fromDate = signal(this.isoDaysAgo(29));
  readonly toDate = signal(this.isoDaysAgo(0));
  readonly providerFilter = signal('');
  readonly modelFilter = signal('');
  readonly sourceFilter = signal('');

  readonly loading = signal(true);
  readonly generating = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  readonly maxTrendCalls = computed(() => {
    const trend = this.data()?.trend ?? [];
    return Math.max(...trend.map((point) => point.calls), 1);
  });

  readonly totalCalls = computed(() =>
    (this.data()?.trend ?? []).reduce((sum, point) => sum + point.calls, 0),
  );

  readonly totalEvaluations = computed(() =>
    (this.data()?.trend ?? []).reduce((sum, point) => sum + point.evaluations, 0),
  );

  readonly totalSecurityFindings = computed(() =>
    (this.data()?.trend ?? []).reduce((sum, point) => sum + point.security_findings, 0),
  );

  readonly modelsForComparison = computed(() => this.modelData()?.models ?? []);

  readonly compareModels = computed(() => {
    const models = this.modelsForComparison();
    const keys = [this.compareA(), this.compareB()].filter(Boolean);
    return keys
      .map((key) => models.find((model) => model.key === key))
      .filter((model): model is ModelPerformance => Boolean(model));
  });

  readonly compareMaxCalls = computed(() => {
    const values = this.compareModels().flatMap((model) =>
      model.trend.map((point) => point.calls),
    );
    return Math.max(...values, 1);
  });

  readonly severityRows = computed(() => {
    const counts = this.data()?.summary.security.severity_counts ?? {};
    return ['critical', 'high', 'medium', 'low', 'info'].map((key) => ({
      key,
      count: counts[key] ?? 0,
    }));
  });

  ngOnInit(): void {
    this.loadProjects();
  }

  selectProject(projectId: string): void {
    if (!projectId || projectId === this.selectedProjectId()) {
      return;
    }
    this.selectedProjectId.set(projectId);
    this.data.set(null);
    this.modelData.set(null);
    this.selectedReport.set(null);
    this.resetMessages();
    this.loadProjectData();
  }

  setFilter(key: keyof AnalyticsFilters, value: string): void {
    const setters: Record<keyof AnalyticsFilters, (next: string) => void> = {
      from: (next) => this.fromDate.set(next),
      to: (next) => this.toDate.set(next),
      provider: (next) => this.providerFilter.set(next),
      model: (next) => this.modelFilter.set(next),
      source: (next) => this.sourceFilter.set(next),
    };
    setters[key](value);
    this.loadAnalytics();
  }

  resetFilters(): void {
    this.fromDate.set(this.isoDaysAgo(29));
    this.toDate.set(this.isoDaysAgo(0));
    this.providerFilter.set('');
    this.modelFilter.set('');
    this.sourceFilter.set('');
    this.loadAnalytics();
  }

  refresh(): void {
    this.loadAnalytics();
    this.loadReports();
  }

  trendBarHeight(point: AnalyticsTrendPoint): number {
    if (!point.calls) {
      return 0;
    }
    return Math.max((point.calls / this.maxTrendCalls()) * 100, 4);
  }

  trendSuccessShare(point: AnalyticsTrendPoint): number {
    return point.calls ? (point.succeeded / point.calls) * 100 : 0;
  }

  trendFailureShare(point: AnalyticsTrendPoint): number {
    return point.calls ? (point.failed / point.calls) * 100 : 0;
  }

  trendTitle(point: AnalyticsTrendPoint): string {
    return `${point.day}: ${point.calls} calls · ${point.succeeded} succeeded · ${point.failed} failed · ${point.executions} executions · ${point.evaluations} evaluations · ${point.security_findings} security findings`;
  }

  modelBarHeight(point: ModelTrendPoint): number {
    return point.calls ? Math.max((point.calls / this.compareMaxCalls()) * 100, 4) : 0;
  }

  modelTrendTitle(point: ModelTrendPoint): string {
    return `${point.day}: ${point.calls} calls · ${point.failed} failed · ${durationText(point.avg_latency_ms)} avg · score ${scoreText(point.avg_evaluation_score)}`;
  }

  modelLabel(model: ModelPerformance): string {
    return `${model.provider_name} · ${model.model_id}`;
  }

  tokens(input: number | null, output: number | null): string {
    if (input === null && output === null) {
      return 'Unavailable';
    }
    return `${this.formatNumber(input)} in / ${this.formatNumber(output)} out`;
  }

  costs(items: AnalyticsCost[] | undefined): string {
    if (!items?.length) {
      return 'Unavailable';
    }
    return items.map((item) => `${item.amount} ${item.currency}`).join(' · ');
  }

  costBadge(status: string): string {
    if (status === 'estimated') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'partial') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-slate-50 text-slate-500';
  }

  statusBadge(status: string): string {
    if (status === 'completed' || status === 'succeeded') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'running' || status === 'queued' || status === 'partial') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-rose-50 text-rose-700';
  }

  severityBar(key: string): string {
    if (key === 'critical') {
      return 'bg-rose-700';
    }
    if (key === 'high') {
      return 'bg-rose-500';
    }
    if (key === 'medium') {
      return 'bg-amber-400';
    }
    return 'bg-slate-300';
  }

  severityPercent(count: number): number {
    const max = Math.max(...this.severityRows().map((row) => row.count), 1);
    return count ? Math.max((count / max) * 100, 4) : 0;
  }

  duration(value: number | null): string {
    return durationText(value);
  }

  score(value: number | null | undefined): string {
    return scoreText(value);
  }

  percent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return 'Unavailable';
    }
    return `${Math.round(value * 100)}%`;
  }

  formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return new Intl.NumberFormat().format(value);
  }

  sourceLabel(source: string | null): string {
    if (source === 'playground') {
      return 'Playground';
    }
    if (source === 'evaluation') {
      return 'Evaluations';
    }
    return 'All sources';
  }

  toggleSection(key: ReportSectionKey): void {
    this.selectedSections.update((sections) =>
      sections.includes(key)
        ? sections.filter((section) => section !== key)
        : [...sections, key],
    );
  }

  selectReport(reportId: string): void {
    this.analyticsService.report(reportId).subscribe({
      next: (report) => this.selectedReport.set(report),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  generateReport(): void {
    const projectId = this.selectedProjectId();
    const d = this.data();
    if (!projectId || !d) {
      return;
    }
    if (!this.selectedSections().length) {
      this.error.set('Choose at least one report section.');
      return;
    }
    const input: AnalyticsReportInput = {
      title: this.reportTitle().trim(),
      from: this.fromDate(),
      to: this.toDate(),
      sections: this.selectedSections(),
    };
    if (this.providerFilter()) {
      input.provider = this.providerFilter();
    }
    if (this.modelFilter()) {
      input.model = this.modelFilter();
    }
    if (this.sourceFilter()) {
      input.source = this.sourceFilter();
    }
    this.generating.set(true);
    this.resetMessages();
    this.analyticsService.createReport(projectId, input).subscribe({
      next: (report) => {
        this.generating.set(false);
        this.notice.set('Report generated from a stored snapshot.');
        this.reports.update((reports) => [report, ...reports]);
        this.selectedReport.set(report);
      },
      error: (error: unknown) => {
        this.generating.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  downloadReport(format: 'csv' | 'pdf'): void {
    const report = this.selectedReport();
    if (!report) {
      return;
    }
    this.analyticsService.exportReport(report.id, format).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `analytics-report-${report.id}.${format}`;
        link.click();
        URL.revokeObjectURL(url);
        this.notice.set(`Report exported as ${format.toUpperCase()}.`);
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
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
              map((projects: Paginated<Project>) =>
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
              this.loadProjectData();
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

  private loadProjectData(): void {
    this.loadAnalytics();
    this.loadReports();
  }

  private loadAnalytics(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      dashboard: this.analyticsService.dashboard(projectId, this.filters()),
      models: this.analyticsService.models(projectId, this.filters()),
    }).subscribe({
      next: ({ dashboard, models }) => {
        this.data.set(dashboard);
        this.modelData.set(models);
        this.ensureComparisonDefaults();
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadReports(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.analyticsService.reports(projectId).subscribe({
      next: (reports) => this.reports.set(reports),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private ensureComparisonDefaults(): void {
    const models = this.modelsForComparison();
    const currentA = this.compareA();
    const currentB = this.compareB();
    if (!models.length) {
      this.compareA.set('');
      this.compareB.set('');
      return;
    }
    if (!models.some((model) => model.key === currentA)) {
      this.compareA.set(models[0].key);
    }
    const nextB = models.find((model) => model.key === currentB);
    if (!nextB || nextB.key === this.compareA()) {
      this.compareB.set(
        models.find((model) => model.key !== this.compareA())?.key ?? '',
      );
    }
  }

  private filters(): AnalyticsFilters {
    return {
      from: this.fromDate(),
      to: this.toDate(),
      provider: this.providerFilter(),
      model: this.modelFilter(),
      source: this.sourceFilter(),
    };
  }

  private isoDaysAgo(daysAgo: number): string {
    const value = new Date();
    value.setDate(value.getDate() - daysAgo);
    const year = value.getFullYear();
    const month = `${value.getMonth() + 1}`.padStart(2, '0');
    const day = `${value.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private resetMessages(): void {
    this.error.set(null);
    this.notice.set(null);
  }
}

function durationText(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Unavailable';
  }
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function scoreText(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return value.toFixed(3);
}
