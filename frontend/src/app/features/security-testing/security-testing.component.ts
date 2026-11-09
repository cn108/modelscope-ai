import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { ProviderConfig, ProviderService } from '../providers/provider.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  SecurityTestCatalog,
  SecurityTestComparison,
  SecurityTestDashboard,
  SecurityTestModelSelection,
  SecurityTestResult,
  SecurityTestRun,
  SecurityTestSeverity,
  SecurityTestingService,
  SecurityTestVerdict,
} from './security-testing.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

interface SelectedModel {
  providerId: string;
  providerName: string;
  modelId: string;
}

const VERDICT_ORDER: SecurityTestVerdict[] = ['failed', 'inconclusive', 'passed', ''];
const SEVERITY_ORDER: SecurityTestSeverity[] = ['critical', 'high', 'medium', 'low', 'info', ''];

@Component({
  selector: 'msa-security-testing',
  standalone: true,
  imports: [LocalDatePipe, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand">
              <msa-icon name="shield" [size]="19" />
            </span>
            <h1 class="msa-h1">AI Security Testing</h1>
          </div>
          <p class="msa-sub">
            Send reviewed attack cases to your configured models, classify the actual
            responses, and compare resistance over time.
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
          <button type="button" class="msa-btn-secondary" [disabled]="loading()" (click)="refresh()">
            <msa-icon name="refresh" [size]="15" /> Refresh
          </button>
        </div>
      </header>

      @if (error()) {
        <p class="msa-card mt-5 flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }
      @if (message()) {
        <p class="msa-card mt-5 flex items-start gap-2 border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
          <msa-icon name="check-circle" [size]="16" />
          <span>{{ message() }}</span>
          <button type="button" class="ml-auto" title="Dismiss" (click)="message.set(null)">
            <msa-icon name="close" [size]="14" />
          </button>
        </p>
      }

      @if (loading() && !dashboard()) {
        <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          @for (placeholder of [1, 2, 3, 4]; track placeholder) {
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
            <msa-icon name="shield" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-md text-sm text-muted">
            Security tests run only against providers configured inside a project you own
            or belong to.
          </p>
        </div>
      } @else {
        @if (dashboard(); as data) {
          <section class="mt-5 rounded-xl border border-amber-200 bg-amber-50/70 p-3.5">
            <p class="flex items-start gap-2 text-xs leading-relaxed text-amber-900">
              <msa-icon name="alert" [size]="15" class="mt-0.5 shrink-0" />
              <span><strong>Evidence, not a guarantee.</strong> {{ data.disclaimer }}</span>
            </p>
          </section>

          <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <article class="msa-card p-5">
              <p class="text-xs font-medium text-muted">Tests performed</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">{{ data.tests_performed }}</p>
              <p class="mt-1 text-[11px] text-slate-400">
                {{ data.runs }} runs · {{ data.running_runs }} queued/running
              </p>
            </article>
            <article class="msa-card p-5">
              <p class="text-xs font-medium text-muted">Passed</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-emerald-600">{{ data.passed }}</p>
              <p class="mt-1 text-[11px] text-slate-400">
                {{ percent(data.pass_rate) }} of decisive results
              </p>
            </article>
            <article class="msa-card p-5">
              <p class="text-xs font-medium text-muted">Vulnerabilities</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-rose-600">{{ data.vulnerabilities }}</p>
              <p class="mt-1 text-[11px] text-slate-400">
                {{ percent(data.fail_rate) }} of decisive results · {{ data.inconclusive }} inconclusive
              </p>
            </article>
            <article class="msa-card p-5">
              <p class="text-xs font-medium text-muted">Decisive coverage</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">{{ percent(data.coverage) }}</p>
              <p class="mt-1 text-[11px] text-slate-400">
                Inconclusive results are never counted as passes
              </p>
            </article>
          </div>

          <div class="mt-4 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Start a controlled test run</h2>
                  <p class="text-xs text-muted">
                    Only reviewed cases and models configured in this project can be used.
                  </p>
                </div>
                <span class="msa-badge bg-brand-soft text-brand">{{ catalog()?.case_count ?? 0 }} reviewed cases</span>
              </div>

              <div class="space-y-4 p-5">
                <div>
                  <p class="msa-label mb-1.5">Models to test</p>
                  <div class="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <select
                      class="msa-input"
                      [value]="modelProviderId()"
                      (change)="selectModelProvider($any($event.target).value)"
                      aria-label="Select provider"
                    >
                      @for (provider of providers(); track provider.id) {
                        <option [value]="provider.id">{{ provider.name }} · {{ provider.kind }}</option>
                      }
                    </select>
                    <select
                      class="msa-input"
                      [value]="modelIdInput()"
                      (change)="modelIdInput.set($any($event.target).value)"
                      aria-label="Select configured model"
                      [disabled]="!availableModels().length"
                    >
                      @for (model of availableModels(); track model.model_id) {
                        <option [value]="model.model_id">
                          {{ model.display_name || model.model_id }}
                        </option>
                      } @empty {
                        <option value="">No configured models</option>
                      }
                    </select>
                    <button
                      type="button"
                      class="msa-btn-secondary"
                      [disabled]="!modelProviderId() || !modelIdInput().trim() || selectedModels().length >= 5"
                      (click)="addModel()"
                    >
                      <msa-icon name="plus" [size]="14" /> Add
                    </button>
                  </div>
                  @if (!providers().length) {
                    <p class="mt-1 text-[11px] text-amber-700">
                      No providers are configured in this project. Add one under Workspaces first.
                    </p>
                  } @else if (!availableModels().length) {
                    <p class="mt-1 text-[11px] text-amber-700">
                      No models are configured for this provider. Add or discover one under
                      Workspaces before testing.
                    </p>
                  }
                  @if (selectedModels().length) {
                    <div class="mt-2 flex flex-wrap gap-1.5">
                      @for (model of selectedModels(); track model.providerId + model.modelId) {
                        <span class="inline-flex items-center gap-1 rounded-lg bg-brand-soft px-2 py-1 text-[11px] text-brand">
                          {{ model.providerName }} · {{ model.modelId }}
                          <button type="button" title="Remove model" (click)="removeModel(model)">
                            <msa-icon name="close" [size]="11" />
                          </button>
                        </span>
                      }
                    </div>
                  }
                </div>

                <div>
                  <div class="flex items-center justify-between">
                    <p class="msa-label">Attack cases</p>
                    <div class="flex gap-2">
                      <button type="button" class="text-[11px] font-medium text-brand" (click)="selectAllCases()">Select all</button>
                      <button type="button" class="text-[11px] font-medium text-slate-500" (click)="clearCases()">Clear</button>
                    </div>
                  </div>
                  <div class="mt-2 space-y-2">
                    @for (category of catalog()?.categories ?? []; track category.key) {
                      <details class="rounded-lg border border-line bg-white" [open]="isCategoryFullySelected(category)">
                        <summary class="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-medium text-ink">
                          <input
                            type="checkbox"
                            class="accent-brand"
                            [checked]="isCategoryFullySelected(category)"
                            (click)="$event.stopPropagation()"
                            (change)="toggleCategory(category)"
                          />
                          <span class="flex-1">{{ category.label }}</span>
                          <span class="text-[10px] font-normal text-slate-400">
                            {{ selectedInCategory(category) }}/{{ category.count }}
                          </span>
                        </summary>
                        <div class="space-y-1 border-t border-line px-3 py-2">
                          @for (testCase of category.cases; track testCase.key) {
                            <label class="flex cursor-pointer items-start gap-2 rounded-md p-1 text-[11px] hover:bg-canvas/60">
                              <input
                                type="checkbox"
                                class="mt-0.5 accent-brand"
                                [checked]="selectedCases().includes(testCase.key)"
                                (change)="toggleCase(testCase.key)"
                              />
                              <span class="flex-1">
                                <span class="block font-medium text-slate-700">{{ testCase.name }}</span>
                                <span class="block text-[10px] leading-snug text-slate-400">{{ testCase.criteria }}</span>
                              </span>
                              <span class="msa-badge" [class]="severityClass(testCase.severity)">{{ testCase.severity }}</span>
                            </label>
                          }
                        </div>
                      </details>
                    }
                  </div>
                </div>

                <div class="grid gap-3 sm:grid-cols-2">
                  <label class="text-xs text-muted">
                    <span class="msa-label mb-1">Temperature (optional)</span>
                    <input
                      class="msa-input"
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      [value]="temperature()"
                      (input)="temperature.set($any($event.target).value)"
                      placeholder="Provider default"
                    />
                  </label>
                  <label class="text-xs text-muted">
                    <span class="msa-label mb-1">Max tokens (optional)</span>
                    <input
                      class="msa-input"
                      type="number"
                      min="1"
                      max="4096"
                      [value]="maxTokens()"
                      (input)="maxTokens.set($any($event.target).value)"
                      placeholder="Provider default"
                    />
                  </label>
                </div>

                <div class="flex flex-wrap items-center justify-between gap-3">
                  <p class="text-[11px] text-slate-400">
                    {{ selectedCases().length }} cases × {{ selectedModels().length }} models =
                    {{ selectedCases().length * selectedModels().length }} model calls
                  </p>
                  <button
                    type="button"
                    class="msa-btn-primary"
                    [disabled]="starting() || !selectedCases().length || !selectedModels().length"
                    (click)="startRun()"
                  >
                    @if (starting()) {
                      <msa-icon name="refresh" [size]="14" class="animate-spin" /> Starting
                    } @else {
                      <msa-icon name="play" [size]="14" /> Run security tests
                    }
                  </button>
                </div>
              </div>
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Detection criteria and limits</h2>
                  <p class="text-xs text-muted">What a pass, failure and inconclusive result means.</p>
                </div>
              </div>
              <div class="space-y-3 p-5 text-[11px] leading-relaxed text-slate-600">
                <p>
                  A <span class="msa-badge bg-rose-50 text-rose-700">failed</span> result means the
                  recorded response matched the case's explicit failure criteria. A
                  <span class="msa-badge bg-slate-100 text-slate-600">passed</span> result means the
                  model refused or produced the required safe marker. Anything else is
                  <span class="msa-badge bg-amber-50 text-amber-700">inconclusive</span>, not a pass.
                </p>
                <p>
                  Cases are fixed and reviewed. The platform will not send arbitrary prompts,
                  contact external systems, or test a provider outside this project.
                </p>
                <ul class="space-y-1.5">
                  @for (limitation of data.limitations; track limitation) {
                    <li class="flex items-start gap-1.5">
                      <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300"></span>
                      <span>{{ limitation }}</span>
                    </li>
                  }
                </ul>
              </div>
            </section>
          </div>

          <div class="mt-4 grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Findings by severity</h2>
                  <p class="text-xs text-muted">Failed tests only. Inconclusive and passed are excluded.</p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">{{ data.failed }} failed</span>
              </div>
              <div class="space-y-2.5 p-5">
                @for (severity of severityOrder; track severity) {
                  <div class="flex items-center gap-3">
                    <span class="w-16 text-[11px] capitalize text-slate-500">{{ severity || 'none' }}</span>
                    <div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div class="h-full rounded-full" [class]="severityBarClass(severity)" [style.width.%]="severityShare(data, severity)"></div>
                    </div>
                    <span class="w-8 text-right text-xs font-semibold text-ink">{{ data.severity_counts[severity] || 0 }}</span>
                  </div>
                }
              </div>
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Results by attack category</h2>
                  <p class="text-xs text-muted">Across completed tests in this project.</p>
                </div>
              </div>
              @if (data.categories.length) {
                <div class="overflow-x-auto">
                  <table class="w-full text-left text-sm">
                    <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                      <tr>
                        <th class="px-5 py-2 font-semibold">Category</th>
                        <th class="px-3 py-2 text-right font-semibold">Passed</th>
                        <th class="px-3 py-2 text-right font-semibold">Failed</th>
                        <th class="px-3 py-2 text-right font-semibold">Inconclusive</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line">
                      @for (category of data.categories; track category.category) {
                        <tr>
                          <td class="px-5 py-2.5 text-xs text-slate-600">{{ category.label }}</td>
                          <td class="px-3 py-2.5 text-right text-xs text-emerald-600">{{ category.passed }}</td>
                          <td class="px-3 py-2.5 text-right text-xs font-semibold text-rose-600">{{ category.failed }}</td>
                          <td class="px-3 py-2.5 text-right text-xs text-amber-600">{{ category.inconclusive }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <p class="px-5 py-8 text-center text-sm text-muted">Run tests to populate category results.</p>
              }
            </section>
          </div>

          <section class="msa-card mt-4 overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Model security comparison</h2>
                <p class="text-xs text-muted">
                  Pass rate uses decisive results. Coverage shows how many tests produced a decisive verdict.
                </p>
              </div>
            </div>
            @if (data.models.length) {
              <div class="overflow-x-auto">
                <table class="w-full text-left text-sm">
                  <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th class="px-5 py-2 font-semibold">Model</th>
                      <th class="px-3 py-2 text-right font-semibold">Tests</th>
                      <th class="px-3 py-2 text-right font-semibold">Passed</th>
                      <th class="px-3 py-2 text-right font-semibold">Failed</th>
                      <th class="px-3 py-2 text-right font-semibold">Inconclusive</th>
                      <th class="px-3 py-2 text-right font-semibold">Pass rate</th>
                      <th class="px-3 py-2 text-right font-semibold">Coverage</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-line">
                    @for (model of data.models; track model.provider_name + model.model_id) {
                      <tr>
                        <td class="px-5 py-3">
                          <p class="text-sm font-medium text-ink">{{ model.model_id }}</p>
                          <p class="text-[11px] text-slate-400">{{ model.provider_name }} · {{ model.provider_kind }}</p>
                        </td>
                        <td class="px-3 py-3 text-right text-xs">{{ model.total }}</td>
                        <td class="px-3 py-3 text-right text-xs text-emerald-600">{{ model.passed }}</td>
                        <td class="px-3 py-3 text-right text-xs font-semibold text-rose-600">{{ model.failed }}</td>
                        <td class="px-3 py-3 text-right text-xs text-amber-600">{{ model.inconclusive }}</td>
                        <td class="px-3 py-3 text-right text-xs font-semibold text-ink">{{ percent(model.pass_rate) }}</td>
                        <td class="px-3 py-3 text-right text-xs text-slate-500">{{ percent(model.coverage) }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">No model results yet.</p>
            }
          </section>

          <div class="mt-4 grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Test run history</h2>
                  <p class="text-xs text-muted">
                    Reruns create a new run and preserve every previous response.
                  </p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">{{ runs().length }}</span>
              </div>
              @if (runs().length) {
                <div class="overflow-x-auto">
                  <table class="w-full text-left text-sm">
                    <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                      <tr>
                        <th class="px-5 py-2 font-semibold">Run</th>
                        <th class="px-3 py-2 font-semibold">Status</th>
                        <th class="px-3 py-2 text-right font-semibold">Progress</th>
                        <th class="px-3 py-2 text-right font-semibold">Pass / fail</th>
                        <th class="px-3 py-2 font-semibold">Created</th>
                        <th class="px-5 py-2 text-right font-semibold">Actions</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line">
                      @for (run of runs(); track run.id) {
                        <tr class="cursor-pointer transition-colors hover:bg-canvas/60" [class.bg-brand-soft]="activeRun()?.id === run.id" (click)="openRun(run)">
                          <td class="px-5 py-3">
                            <p class="text-sm font-medium text-ink">Run {{ shortId(run.id) }}</p>
                            <p class="text-[11px] text-slate-400">
                              {{ run.total_models }} models · {{ run.total_cases }} cases · {{ run.categories.length }} categories
                            </p>
                          </td>
                          <td class="px-3 py-3">
                            <span class="msa-badge" [class]="runStatusClass(run.status)">{{ run.status }}</span>
                          </td>
                          <td class="px-3 py-3 text-right text-[11px] text-slate-500">
                            {{ run.completed_results }}/{{ run.total_results }}
                            <span class="block text-[10px] text-slate-400">{{ run.progress }}%</span>
                          </td>
                          <td class="px-3 py-3 text-right text-xs">
                            <span class="text-emerald-600">{{ run.summary.totals?.passed ?? 0 }}</span>
                            <span class="text-slate-300"> / </span>
                            <span class="font-semibold text-rose-600">{{ run.summary.totals?.failed ?? 0 }}</span>
                          </td>
                          <td class="px-3 py-3 text-[11px] text-slate-500">
                            {{ (run.started_at || run.created_at) | msaDate: 'short' }}
                          </td>
                          <td class="px-5 py-3 text-right">
                            <button type="button" class="msa-btn-ghost" title="Rerun this configuration" (click)="$event.stopPropagation(); rerun(run)">
                              <msa-icon name="refresh" [size]="13" /> Rerun
                            </button>
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <p class="px-5 py-8 text-center text-sm text-muted">
                  No security tests yet. Select models and cases above to start.
                </p>
              }
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Latest failures</h2>
                  <p class="text-xs text-muted">Only explicit detector matches appear here.</p>
                </div>
              </div>
              <div class="divide-y divide-line">
                @for (failure of data.recent_failures; track failure.id) {
                  <button type="button" class="block w-full px-5 py-3 text-left hover:bg-canvas/60" (click)="openResultById(failure.id)">
                    <span class="flex items-center gap-1.5">
                      <span class="msa-badge" [class]="severityClass(failure.severity)">{{ failure.severity }}</span>
                      <span class="truncate text-xs font-medium text-ink">{{ failure.case_name }}</span>
                    </span>
                    <span class="mt-1 block truncate text-[10px] text-slate-400">
                      {{ failure.model_id }} · {{ failure.provider_name }} · {{ failure.executed_at | msaDate: 'short' }}
                    </span>
                  </button>
                } @empty {
                  <p class="px-5 py-8 text-center text-sm text-muted">No failed tests recorded.</p>
                }
              </div>
            </section>
          </div>

          @if (activeRun(); as run) {
            <section class="msa-card mt-4 overflow-hidden">
              <div class="msa-card-header flex-wrap gap-2">
                <div>
                  <h2 class="msa-section-title">Run {{ shortId(run.id) }} results</h2>
                  <p class="text-xs text-muted">
                    {{ run.status }} · {{ run.completed_results }}/{{ run.total_results }} complete · {{ run.created_at | msaDate: 'medium' }}
                  </p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <select class="msa-input text-xs" [value]="resultFilterModel()" (change)="setResultFilter('model', $any($event.target).value)" aria-label="Filter results by model">
                    <option value="">All models</option>
                    @for (model of run.models; track model.id) {
                      <option [value]="model.id">{{ model.model_id }} · {{ model.provider_name }}</option>
                    }
                  </select>
                  <select class="msa-input text-xs" [value]="resultFilterVerdict()" (change)="setResultFilter('verdict', $any($event.target).value)" aria-label="Filter results by verdict">
                    <option value="">All verdicts</option>
                    <option value="failed">Failed</option>
                    <option value="inconclusive">Inconclusive</option>
                    <option value="passed">Passed</option>
                  </select>
                  <select class="msa-input max-w-[220px] text-xs" [value]="resultFilterCategory()" (change)="setResultFilter('category', $any($event.target).value)" aria-label="Filter results by category">
                    <option value="">All categories</option>
                    @for (category of run.summary.categories ?? []; track category.category) {
                      <option [value]="category.category">{{ category.label }}</option>
                    }
                  </select>
                  <button type="button" class="msa-btn-ghost" (click)="closeRun()">
                    <msa-icon name="close" [size]="13" /> Close
                  </button>
                </div>
              </div>

              @if (resultsPage()?.results?.length) {
                <div class="overflow-x-auto">
                  <table class="w-full text-left text-sm">
                    <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                      <tr>
                        <th class="px-5 py-2 font-semibold">Case</th>
                        <th class="px-3 py-2 font-semibold">Model</th>
                        <th class="px-3 py-2 font-semibold">Verdict</th>
                        <th class="px-3 py-2 font-semibold">Severity</th>
                        <th class="px-3 py-2 font-semibold">Why</th>
                        <th class="px-5 py-2 text-right font-semibold">Executed</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line">
                      @for (result of resultsPage()!.results; track result.id) {
                        <tr class="cursor-pointer transition-colors hover:bg-canvas/60" (click)="openResultById(result.id)">
                          <td class="px-5 py-3">
                            <p class="text-sm font-medium text-ink">{{ result.case_name }}</p>
                            <p class="text-[11px] text-slate-400">{{ result.category_label }} · {{ result.technique }}</p>
                          </td>
                          <td class="px-3 py-3 text-xs text-slate-600">
                            {{ result.model_id }}
                            <span class="block text-[10px] text-slate-400">{{ result.provider_name }}</span>
                          </td>
                          <td class="px-3 py-3"><span class="msa-badge" [class]="verdictClass(result.verdict)">{{ result.verdict || result.status }}</span></td>
                          <td class="px-3 py-3">
                            @if (result.severity) {
                              <span class="msa-badge" [class]="severityClass(result.severity)">{{ result.severity }}</span>
                            } @else {
                              <span class="text-[11px] text-slate-400">—</span>
                            }
                          </td>
                          <td class="max-w-[320px] px-3 py-3 text-[11px] text-slate-500">{{ result.rationale }}</td>
                          <td class="px-5 py-3 text-right text-[11px] text-slate-500">{{ (result.executed_at || result.created_at) | msaDate: 'short' }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
                <div class="flex items-center justify-between border-t border-line px-5 py-3">
                  <span class="text-[11px] text-slate-400">
                    Page {{ resultPageNumber() }} of {{ resultTotalPages() }}
                  </span>
                  <div class="flex gap-2">
                    <button type="button" class="msa-btn-ghost" [disabled]="!resultsPage()?.previous" (click)="goToResultPage(resultPageNumber() - 1)">Previous</button>
                    <button type="button" class="msa-btn-ghost" [disabled]="!resultsPage()?.next" (click)="goToResultPage(resultPageNumber() + 1)">Next</button>
                  </div>
                </div>
              } @else {
                <p class="px-5 py-8 text-center text-sm text-muted">
                  @if (run.status === 'queued' || run.status === 'running') {
                    Tests are running. Results will appear automatically.
                  } @else {
                    No results match these filters.
                  }
                </p>
              }
            </section>

            <section class="msa-card mt-4 overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Compare historical runs</h2>
                  <p class="text-xs text-muted">
                    See new, resolved and persisting failures between two runs.
                  </p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">Review aid</span>
              </div>
              @if (runs().length < 2) {
                <p class="px-5 py-8 text-center text-sm text-muted">
                  Run the same tests twice to compare changes over time.
                </p>
              } @else {
                <div class="grid gap-3 border-b border-line bg-canvas/40 p-5 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
                  <label class="text-xs text-muted">
                    <span class="msa-label mb-1">Baseline (older)</span>
                    <select class="msa-input" (change)="compareBaselineId.set($any($event.target).value)" aria-label="Baseline run">
                      @for (run of runs(); track run.id) {
                        <option [value]="run.id" [selected]="run.id === compareBaselineId()">Run {{ shortId(run.id) }} · {{ run.created_at | msaDate: 'short' }}</option>
                      }
                    </select>
                  </label>
                  <label class="text-xs text-muted">
                    <span class="msa-label mb-1">Current (newer)</span>
                    <select class="msa-input" (change)="compareCurrentId.set($any($event.target).value)" aria-label="Current run">
                      @for (run of runs(); track run.id) {
                        <option [value]="run.id" [selected]="run.id === compareCurrentId()">Run {{ shortId(run.id) }} · {{ run.created_at | msaDate: 'short' }}</option>
                      }
                    </select>
                  </label>
                  <button type="button" class="msa-btn-primary" [disabled]="comparing() || compareBaselineId() === compareCurrentId()" (click)="runComparison()">
                    @if (comparing()) {
                      <msa-icon name="refresh" [size]="14" class="animate-spin" /> Comparing
                    } @else {
                      <msa-icon name="layers" [size]="14" /> Compare
                    }
                  </button>
                </div>
                @if (compareError()) {
                  <p class="border-b border-rose-100 bg-rose-50 p-3 text-sm text-rose-700" role="alert">{{ compareError() }}</p>
                }
                @if (comparison(); as cmp) {
                  <div class="p-5">
                    <div class="grid gap-3 sm:grid-cols-4">
                      <div class="rounded-xl border border-amber-100 bg-amber-50/60 p-3">
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-700">New failures</p>
                        <p class="mt-1 text-2xl font-semibold text-amber-800">{{ cmp.counts.new_failures }}</p>
                      </div>
                      <div class="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">Resolved</p>
                        <p class="mt-1 text-2xl font-semibold text-emerald-800">{{ cmp.counts.resolved_failures }}</p>
                      </div>
                      <div class="rounded-xl border border-sky-100 bg-sky-50/60 p-3">
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-sky-700">Persisting</p>
                        <p class="mt-1 text-2xl font-semibold text-sky-800">{{ cmp.counts.persisting_failures }}</p>
                      </div>
                      <div class="rounded-xl border border-line p-3">
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Changed verdicts</p>
                        <p class="mt-1 text-2xl font-semibold text-ink">{{ cmp.counts.changed_verdicts }}</p>
                      </div>
                    </div>
                    @for (warning of cmp.warnings; track warning) {
                      <p class="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-800">
                        <msa-icon name="alert" [size]="13" class="mt-0.5 shrink-0" /> {{ warning }}
                      </p>
                    }
                    <div class="mt-4 grid gap-3 lg:grid-cols-3">
                      @for (bucket of comparisonBuckets(cmp); track bucket.key) {
                        <section class="overflow-hidden rounded-xl border border-line">
                          <div class="flex items-center justify-between bg-canvas/50 px-3 py-2">
                            <h3 class="text-xs font-semibold text-ink">{{ bucket.label }}</h3>
                            <span class="msa-badge bg-white text-slate-600">{{ bucket.items.length }}</span>
                          </div>
                          <div class="divide-y divide-line">
                            @for (item of bucket.items; track item.case_key + (item.current?.id ?? item.baseline?.id ?? '')) {
                              <button type="button" class="block w-full px-3 py-2 text-left hover:bg-canvas/60" (click)="openComparisonResult(item)">
                                <span class="block truncate text-xs font-medium text-ink">{{ item.current?.case_name || item.baseline?.case_name }}</span>
                                <span class="block truncate text-[10px] text-slate-400">
                                  {{ item.current?.model_id || item.baseline?.model_id }} ·
                                  {{ item.baseline?.verdict || 'absent' }} → {{ item.current?.verdict || 'absent' }}
                                </span>
                              </button>
                            } @empty {
                              <p class="px-3 py-5 text-center text-[11px] text-muted">None.</p>
                            }
                          </div>
                        </section>
                      }
                    </div>
                  </div>
                }
              }
            </section>
          }
        }
      }
    </div>

    @if (selectedResult(); as result) {
      <div class="fixed inset-0 z-50 flex justify-end bg-navy/40 backdrop-blur-sm" (click)="selectedResult.set(null)">
        <aside class="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl" (click)="$event.stopPropagation()">
          <div class="sticky top-0 flex items-start justify-between gap-3 border-b border-line bg-white px-5 py-4">
            <div>
              <p class="text-[11px] uppercase tracking-wide text-slate-400">{{ result.category_label }}</p>
              <h2 class="mt-0.5 text-lg font-semibold text-ink">{{ result.case_name }}</h2>
              <p class="mt-1 text-xs text-muted">{{ result.provider_name }} · {{ result.model_id }}</p>
            </div>
            <button type="button" class="msa-icon-btn" title="Close result" (click)="selectedResult.set(null)">
              <msa-icon name="close" [size]="18" />
            </button>
          </div>
          <div class="space-y-4 p-5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="msa-badge" [class]="verdictClass(result.verdict)">{{ result.verdict || result.status }}</span>
              @if (result.severity) {
                <span class="msa-badge" [class]="severityClass(result.severity)">{{ result.severity }}</span>
              }
              <span class="text-[11px] text-slate-400">{{ result.executed_at | msaDate: 'medium' }}</span>
              @if (result.duration_ms !== null) {
                <span class="text-[11px] text-slate-400">{{ result.duration_ms }} ms</span>
              }
            </div>

            <section class="rounded-xl border border-line p-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Classification</h3>
              <p class="mt-1 text-sm leading-relaxed text-slate-700">{{ result.rationale }}</p>
              @if (result.evidence) {
                <p class="mt-2 rounded-lg bg-canvas/60 p-2 font-mono text-[11px] text-slate-600">{{ result.evidence }}</p>
              }
              <p class="mt-2 text-[10px] text-slate-400">
                Matched rules: {{ result.matched_rules.join(', ') || 'none' }}
              </p>
            </section>

            <section>
              <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Why this case classifies that way</h3>
              <p class="mt-1 text-xs leading-relaxed text-slate-600">{{ result.criteria }}</p>
            </section>

            <section>
              <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">System context sent</h3>
              <pre class="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-navy p-3 text-[11px] leading-relaxed text-slate-200">{{ result.system_prompt || 'No system message was sent.' }}</pre>
            </section>

            <section>
              <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Attack input sent</h3>
              <pre class="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-navy p-3 text-[11px] leading-relaxed text-slate-200">{{ result.attack_input }}</pre>
            </section>

            <section>
              <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Actual model response</h3>
              @if (result.response_text) {
                <pre class="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-canvas/50 p-3 text-[11px] leading-relaxed text-slate-700">{{ result.response_text }}</pre>
              } @else {
                <p class="mt-1 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                  No response was recorded. {{ result.error?.message || 'The provider call did not return content.' }}
                </p>
              }
            </section>

            <section class="rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-emerald-700">Recommended mitigation</h3>
              <p class="mt-1 text-xs leading-relaxed text-emerald-900">{{ result.mitigation }}</p>
            </section>

            @if (result.references?.length) {
              <section>
                <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">References</h3>
                <ul class="mt-1 list-disc space-y-1 pl-4 text-[11px] text-slate-500">
                  @for (reference of result.references; track reference) {
                    <li>{{ reference }}</li>
                  }
                </ul>
              </section>
            }
          </div>
        </aside>
      </div>
    }
  `,
})
export class SecurityTestingComponent implements OnInit, OnDestroy {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly providerService = inject(ProviderService);
  private readonly testing = inject(SecurityTestingService);

  readonly severityOrder = SEVERITY_ORDER;
  readonly verdictOrder = VERDICT_ORDER;

  readonly workspaces = signal<Workspace[]>([]);
  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly providers = signal<ProviderConfig[]>([]);
  readonly catalog = signal<SecurityTestCatalog | null>(null);
  readonly dashboard = signal<SecurityTestDashboard | null>(null);
  readonly runs = signal<SecurityTestRun[]>([]);
  readonly activeRun = signal<SecurityTestRun | null>(null);
  readonly resultsPage = signal<Paginated<SecurityTestResult> | null>(null);
  readonly resultPageNumber = signal(1);
  readonly selectedResult = signal<SecurityTestResult | null>(null);
  readonly comparison = signal<SecurityTestComparison | null>(null);

  readonly selectedCases = signal<string[]>([]);
  readonly selectedModels = signal<SelectedModel[]>([]);
  readonly modelProviderId = signal('');
  readonly modelIdInput = signal('');
  readonly temperature = signal('');
  readonly maxTokens = signal('');

  readonly resultFilterModel = signal('');
  readonly resultFilterVerdict = signal('');
  readonly resultFilterCategory = signal('');
  readonly compareBaselineId = signal('');
  readonly compareCurrentId = signal('');
  readonly comparing = signal(false);
  readonly compareError = signal<string | null>(null);

  readonly loading = signal(true);
  readonly starting = signal(false);
  readonly error = signal<string | null>(null);
  readonly message = signal<string | null>(null);

  readonly availableModels = computed(() => {
    const provider = this.providers().find((item) => item.id === this.modelProviderId());
    return provider?.models ?? [];
  });

  readonly resultTotalPages = computed(() => {
    const page = this.resultsPage();
    return page ? Math.max(1, Math.ceil(page.count / 50)) : 1;
  });

  private pollHandle: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.loadCatalog();
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
    this.activeRun.set(null);
    this.resultsPage.set(null);
    this.comparison.set(null);
    this.selectedResult.set(null);
    this.resultFilterModel.set('');
    this.resultFilterVerdict.set('');
    this.resultFilterCategory.set('');
    this.loadProjectData();
  }

  refresh(): void {
    this.loadProjectData();
  }

  isCategoryFullySelected(category: { cases: { key: string }[] }): boolean {
    const selected = this.selectedCases();
    return category.cases.length > 0 && category.cases.every((testCase) => selected.includes(testCase.key));
  }

  selectedInCategory(category: { cases: { key: string }[] }): number {
    const selected = this.selectedCases();
    return category.cases.filter((testCase) => selected.includes(testCase.key)).length;
  }

  toggleCategory(category: { cases: { key: string }[] }): void {
    const keys = category.cases.map((testCase) => testCase.key);
    const selected = this.selectedCases();
    const all = keys.every((key) => selected.includes(key));
    this.selectedCases.set(
      all ? selected.filter((key) => !keys.includes(key)) : [...new Set([...selected, ...keys])],
    );
  }

  toggleCase(key: string): void {
    const selected = this.selectedCases();
    this.selectedCases.set(
      selected.includes(key) ? selected.filter((item) => item !== key) : [...selected, key],
    );
  }

  selectAllCases(): void {
    this.selectedCases.set(
      (this.catalog()?.categories ?? []).flatMap((category) =>
        category.cases.map((testCase) => testCase.key),
      ),
    );
  }

  clearCases(): void {
    this.selectedCases.set([]);
  }

  selectModelProvider(providerId: string): void {
    this.modelProviderId.set(providerId);
    this.modelIdInput.set(this.availableModels()[0]?.model_id ?? '');
  }

  addModel(): void {
    const provider = this.providers().find((item) => item.id === this.modelProviderId());
    const modelId = this.modelIdInput().trim();
    if (!provider || !modelId) {
      return;
    }
    if (!provider.models.some((model) => model.model_id === modelId)) {
      this.error.set('Select a model configured for this provider.');
      return;
    }
    if (this.selectedModels().length >= 5) {
      this.error.set('Select at most 5 models per run.');
      return;
    }
    if (this.selectedModels().some((item) => item.providerId === provider.id && item.modelId === modelId)) {
      this.error.set('That model is already selected.');
      return;
    }
    this.selectedModels.set([
      ...this.selectedModels(),
      { providerId: provider.id, providerName: provider.name, modelId },
    ]);
    this.modelIdInput.set('');
    this.error.set(null);
  }

  removeModel(model: SelectedModel): void {
    this.selectedModels.set(
      this.selectedModels().filter(
        (item) => !(item.providerId === model.providerId && item.modelId === model.modelId),
      ),
    );
  }

  startRun(): void {
    const projectId = this.selectedProjectId();
    const cases = this.selectedCases();
    const selected = this.selectedModels();
    if (!projectId || !cases.length || !selected.length) {
      this.error.set('Choose a project, at least one model and at least one attack case.');
      return;
    }
    const parameters: Record<string, unknown> = {};
    const temperature = Number(this.temperature());
    if (this.temperature().trim() && Number.isFinite(temperature)) {
      parameters['temperature'] = temperature;
    }
    const maxTokens = Number(this.maxTokens());
    if (this.maxTokens().trim() && Number.isFinite(maxTokens) && maxTokens > 0) {
      parameters['max_tokens'] = Math.round(maxTokens);
    }
    const models: SecurityTestModelSelection[] = selected.map((model) => ({
      provider: model.providerId,
      model_id: model.modelId,
    }));
    this.starting.set(true);
    this.error.set(null);
    this.message.set(null);
    this.testing
      .createRun(projectId, { models, cases, parameters })
      .subscribe({
        next: (run) => {
          this.starting.set(false);
          this.activeRun.set(run);
          this.resultPageNumber.set(1);
          this.resultFilterModel.set('');
          this.resultFilterVerdict.set('');
          this.resultFilterCategory.set('');
          this.message.set(
            run.status === 'completed'
              ? `Run completed: ${run.summary.totals?.passed ?? 0} passed and ${run.summary.totals?.failed ?? 0} failed.`
              : 'Run queued. Progress will update automatically.',
          );
          this.loadData();
          this.loadResults();
          if (run.status === 'queued' || run.status === 'running') {
            this.startPolling();
          }
        },
        error: (error: unknown) => {
          this.starting.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  openRun(run: SecurityTestRun): void {
    this.activeRun.set(run);
    this.resultPageNumber.set(1);
    this.resultFilterModel.set('');
    this.resultFilterVerdict.set('');
    this.resultFilterCategory.set('');
    this.comparison.set(null);
    this.loadResults();
  }

  closeRun(): void {
    this.activeRun.set(null);
    this.resultsPage.set(null);
    this.comparison.set(null);
    this.stopPolling();
  }

  rerun(run: SecurityTestRun): void {
    this.error.set(null);
    this.message.set(null);
    this.testing.rerun(run.id).subscribe({
      next: (created) => {
        this.activeRun.set(created);
        this.resultPageNumber.set(1);
        this.message.set('Rerun started. The previous run and every result were preserved.');
        this.loadData();
        this.loadResults();
        if (created.status === 'queued' || created.status === 'running') {
          this.startPolling();
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  setResultFilter(key: 'model' | 'verdict' | 'category', value: string): void {
    if (key === 'model') {
      this.resultFilterModel.set(value);
    } else if (key === 'verdict') {
      this.resultFilterVerdict.set(value);
    } else {
      this.resultFilterCategory.set(value);
    }
    this.resultPageNumber.set(1);
    this.loadResults();
  }

  goToResultPage(page: number): void {
    if (page < 1) {
      return;
    }
    this.resultPageNumber.set(page);
    this.loadResults();
  }

  openResultById(resultId: string): void {
    this.testing.result(resultId).subscribe({
      next: (result) => this.selectedResult.set(result),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  openComparisonResult(item: { current: SecurityTestResult | null; baseline: SecurityTestResult | null }): void {
    const result = item.current ?? item.baseline;
    if (result) {
      this.openResultById(result.id);
    }
  }

  runComparison(): void {
    const projectId = this.selectedProjectId();
    const baseline = this.compareBaselineId();
    const current = this.compareCurrentId();
    if (!projectId || !baseline || !current || baseline === current) {
      this.compareError.set('Choose two different runs to compare.');
      return;
    }
    this.comparing.set(true);
    this.compareError.set(null);
    this.testing.compare(projectId, baseline, current).subscribe({
      next: (comparison) => {
        this.comparison.set(comparison);
        this.comparing.set(false);
      },
      error: (error: unknown) => {
        this.comparing.set(false);
        this.compareError.set(apiErrorMessage(error));
      },
    });
  }

  comparisonBuckets(comparison: SecurityTestComparison) {
    return [
      { key: 'new', label: 'New failures', items: comparison.new_failures },
      { key: 'resolved', label: 'Resolved failures', items: comparison.resolved_failures },
      { key: 'persisting', label: 'Persisting failures', items: comparison.persisting },
    ];
  }

  percent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return `${Math.round(value * 100)}%`;
  }

  severityShare(data: SecurityTestDashboard, severity: string): number {
    if (!data.failed) {
      return 0;
    }
    return Math.round(((data.severity_counts[severity] || 0) / data.failed) * 100);
  }

  severityBarClass(severity: string): string {
    if (severity === 'critical') return 'bg-rose-500';
    if (severity === 'high') return 'bg-orange-400';
    if (severity === 'medium') return 'bg-amber-400';
    if (severity === 'low') return 'bg-sky-400';
    return 'bg-slate-300';
  }

  severityClass(severity: string): string {
    if (severity === 'critical') return 'bg-rose-100 text-rose-800';
    if (severity === 'high') return 'bg-orange-100 text-orange-800';
    if (severity === 'medium') return 'bg-amber-100 text-amber-800';
    if (severity === 'low') return 'bg-sky-100 text-sky-800';
    return 'bg-slate-100 text-slate-600';
  }

  verdictClass(verdict: string): string {
    if (verdict === 'failed') return 'bg-rose-100 text-rose-800';
    if (verdict === 'passed') return 'bg-emerald-100 text-emerald-800';
    if (verdict === 'inconclusive') return 'bg-amber-100 text-amber-800';
    return 'bg-slate-100 text-slate-600';
  }

  runStatusClass(status: string): string {
    if (status === 'completed') return 'bg-emerald-50 text-emerald-700';
    if (status === 'failed') return 'bg-rose-50 text-rose-700';
    if (status === 'running') return 'bg-sky-50 text-sky-700';
    return 'bg-slate-50 text-slate-500';
  }

  shortId(value: string): string {
    return value.slice(0, 8);
  }

  private loadCatalog(): void {
    this.testing.catalog().subscribe({
      next: (catalog) => {
        this.catalog.set(catalog);
        this.selectAllCases();
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
            if (projects[0]) {
              this.selectedProjectId.set(projects[0].id);
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
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loadProviders();
    this.loadData();
  }

  private loadProviders(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.providerService.list(projectId).subscribe({
      next: (providers) => {
        this.providers.set(providers);
        if (!providers.some((provider) => provider.id === this.modelProviderId())) {
          this.modelProviderId.set(providers[0]?.id ?? '');
        }
        const selected = providers.find((provider) => provider.id === this.modelProviderId());
        const known = selected?.models.map((model) => model.model_id) ?? [];
        if (!known.includes(this.modelIdInput())) {
          this.modelIdInput.set(known[0] ?? '');
        }
      },
      error: () => this.providers.set([]),
    });
  }

  private loadData(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      dashboard: this.testing.dashboard(projectId),
      runs: this.testing.runs(projectId),
    }).subscribe({
      next: ({ dashboard, runs }) => {
        this.dashboard.set(dashboard);
        this.runs.set(runs);
        this.ensureCompareDefaults();
        this.loading.set(false);
        if (this.activeRun()) {
          const refreshed = runs.find((run) => run.id === this.activeRun()!.id);
          if (refreshed) {
            this.activeRun.set(refreshed);
            if (refreshed.status === 'completed' || refreshed.status === 'failed') {
              this.loadResults();
              this.stopPolling();
            }
          }
        }
        if (!dashboard.running_runs) {
          this.stopPolling();
        }
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
        this.stopPolling();
      },
    });
  }

  private loadResults(): void {
    const run = this.activeRun();
    if (!run) {
      return;
    }
    this.testing
      .results(
        run.id,
        {
          model: this.resultFilterModel(),
          verdict: this.resultFilterVerdict(),
          category: this.resultFilterCategory(),
        },
        this.resultPageNumber(),
      )
      .subscribe({
        next: (page) => this.resultsPage.set(page),
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
  }

  private ensureCompareDefaults(): void {
    const rows = this.runs();
    if (rows.length < 2) {
      this.compareBaselineId.set(rows[0]?.id ?? '');
      this.compareCurrentId.set('');
      return;
    }
    if (!rows.some((run) => run.id === this.compareCurrentId())) {
      this.compareCurrentId.set(rows[0].id);
    }
    const current = rows.find((run) => run.id === this.compareCurrentId()) ?? rows[0];
    const options = rows.filter(
      (run) =>
        run.id !== current.id &&
        new Date(run.created_at).getTime() <= new Date(current.created_at).getTime(),
    );
    if (!options.some((run) => run.id === this.compareBaselineId())) {
      this.compareBaselineId.set(options[0]?.id ?? '');
    }
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandle = setInterval(() => {
      this.loadData();
      if (this.activeRun()?.status === 'queued' || this.activeRun()?.status === 'running') {
        this.loadResults();
      }
    }, 2500);
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }
}
