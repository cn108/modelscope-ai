import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { Dataset, DatasetService } from '../datasets/dataset.service';
import { Execution, PlaygroundService, SavedPrompt } from '../playground/playground.service';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import { SecurityFindingDetailComponent } from './security-finding-detail.component';
import {
  SecurityCheckCatalog,
  SecurityDashboard,
  SecurityFinding,
  SecurityScan,
  SecurityScanComparison,
  SecurityService,
  SecuritySeverity,
  SecurityTargetType,
} from './security.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

interface TargetOption {
  id: string;
  label: string;
  detail: string;
}

@Component({
  selector: 'msa-security',
  standalone: true,
  imports: [DatePipe, RouterLink, IconComponent, SecurityFindingDetailComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand">
              <msa-icon name="shield" [size]="19" />
            </span>
            <h1 class="msa-h1">Security</h1>
          </div>
          <p class="msa-sub">
            Scan prompts, datasets and execution records for potential PII, prompt injection
            and unsafe output risks.
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
          <button type="button" class="ml-auto text-emerald-700" title="Dismiss" (click)="message.set(null)">
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
          <p class="mt-1 max-w-sm text-sm text-muted">
            Security scans are attached to existing datasets, prompts and executions in a project.
          </p>
          <a class="msa-btn-primary mt-4" routerLink="/workspaces">
            <msa-icon name="plus" [size]="14" /> Go to Workspaces
          </a>
        </div>
      } @else {
        @if (dashboard(); as data) {
        <section class="mt-5 rounded-xl border border-amber-200 bg-amber-50/70 p-3.5">
          <p class="flex items-start gap-2 text-xs leading-relaxed text-amber-900">
            <msa-icon name="alert" [size]="15" class="mt-0.5 shrink-0" />
            <span>
              <strong>Detection aids, not a security guarantee.</strong>
              {{ data.disclaimer }}
            </span>
          </p>
        </section>

        <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Security scans</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">{{ data.scans }}</p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ data.completed_scans }} completed · {{ data.running_scans }} queued/running
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">All findings</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">{{ data.findings }}</p>
            <p class="mt-1 text-[11px] text-slate-400">
              {{ data.open_findings }} open · {{ data.reviewed_findings }} reviewed
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Resolved</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-emerald-600">{{ data.resolved_findings }}</p>
            <p class="mt-1 text-[11px] text-slate-400">Original detections remain in history</p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Blocking findings</p>
            <p class="mt-1 text-2xl font-semibold tracking-tight text-rose-600">{{ data.blocking_findings }}</p>
            <p class="mt-1 text-[11px] text-slate-400">
              Only labelled when a scan explicitly opts in
            </p>
          </article>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Start a controlled scan</h2>
                <p class="text-xs text-muted">
                  Scans run asynchronously against existing resources and never interrupt model execution.
                </p>
              </div>
              <span class="msa-badge bg-brand-soft text-brand">Repeatable</span>
            </div>

            <div class="space-y-4 p-5">
              <div>
                <p class="msa-label mb-1.5">Target type</p>
                <div class="flex flex-wrap gap-1.5">
                  @for (type of targetTypes; track type.key) {
                    <button
                      type="button"
                      class="rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
                      [class]="targetType() === type.key ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-white text-slate-600 hover:border-slate-300'"
                      (click)="setTargetType(type.key)"
                    >
                      <msa-icon [name]="type.icon" [size]="13" class="mr-1 inline" />
                      {{ type.label }}
                    </button>
                  }
                </div>
              </div>

              <label class="block text-xs text-muted">
                <span class="msa-label mb-1">Target</span>
                <select
                  class="msa-input"
                  [value]="effectiveTargetId()"
                  (change)="targetId.set($any($event.target).value)"
                  aria-label="Select scan target"
                >
                  <option value="">Select a {{ targetTypeLabel().toLowerCase() }}</option>
                  @for (target of targetOptions(); track target.id) {
                    <option [value]="target.id" [selected]="target.id === effectiveTargetId()">
                      {{ target.label }} · {{ target.detail }}
                    </option>
                  }
                </select>
                @if (!targetOptions().length) {
                  <span class="mt-1 block text-[11px] text-amber-700">
                    No {{ targetTypeLabel().toLowerCase() }} resources exist in this project yet.
                  </span>
                }
              </label>

              <div>
                <p class="msa-label mb-1.5">Checks to run</p>
                <div class="grid gap-2 sm:grid-cols-3">
                  @for (check of checks(); track check.key) {
                    <label class="flex cursor-pointer items-start gap-2 rounded-lg border border-line p-2.5 text-xs hover:border-brand/40">
                      <input
                        type="checkbox"
                        class="mt-0.5 accent-brand"
                        [checked]="selectedChecks().includes(check.key)"
                        (change)="toggleCheck(check.key)"
                      />
                      <span>
                        <span class="block font-medium text-ink">{{ check.label }}</span>
                        <span class="mt-0.5 block text-[10px] leading-snug text-slate-400">
                          {{ check.limitation }}
                        </span>
                      </span>
                    </label>
                  }
                </div>
                @if (!checks().length) {
                  <p class="text-[11px] text-slate-400">Loading supported checks…</p>
                }
              </div>

              @if (selectedChecks().includes('pii')) {
                <div class="rounded-lg border border-line bg-canvas/40 p-3">
                  <p class="msa-label mb-1.5">PII categories</p>
                  <div class="flex flex-wrap gap-x-4 gap-y-2">
                    @for (category of catalog()?.pii_categories ?? []; track category.key) {
                      <label class="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
                        <input
                          type="checkbox"
                          class="accent-brand"
                          [checked]="selectedPiiCategories().includes(category.key)"
                          (change)="togglePiiCategory(category.key)"
                        />
                        {{ category.label }}
                        <span class="msa-badge bg-slate-100 text-[9px] text-slate-500">{{ category.severity }}</span>
                      </label>
                    }
                  </div>
                  <p class="mt-2 text-[10px] text-slate-400">
                    Only redacted evidence is stored. Categories can be narrowed for this scan.
                  </p>
                </div>
              }

              <div class="rounded-lg border border-line p-3">
                <label class="flex cursor-pointer items-start gap-2 text-xs">
                  <input
                    type="checkbox"
                    class="mt-0.5 accent-brand"
                    [checked]="blockingEnabled()"
                    (change)="blockingEnabled.set($any($event.target).checked)"
                  />
                  <span>
                    <span class="block font-medium text-ink">Label findings at or above a severity as blocking</span>
                    <span class="mt-0.5 block text-[10px] leading-snug text-slate-400">
                      This only labels findings. It does not pause, block or alter normal model execution.
                    </span>
                  </span>
                </label>
                @if (blockingEnabled()) {
                  <div class="mt-3 grid gap-3 sm:grid-cols-[160px_1fr]">
                    <label class="text-xs text-muted">
                      <span class="msa-label mb-1">Blocking severity</span>
                      <select class="msa-input" [value]="blockingSeverity()" (change)="blockingSeverity.set($any($event.target).value)">
                        <option value="medium">Medium and above</option>
                        <option value="high">High and above</option>
                        <option value="critical">Critical only</option>
                      </select>
                    </label>
                    <label class="text-xs text-muted">
                      <span class="msa-label mb-1">Justification (required)</span>
                      <input
                        class="msa-input"
                        [value]="blockingReason()"
                        (input)="blockingReason.set($any($event.target).value)"
                        placeholder="Why should this scan label findings as blocking?"
                      />
                    </label>
                  </div>
                }
              </div>

              <div class="flex flex-wrap items-center justify-between gap-3">
                <p class="text-[11px] text-slate-400">
                  {{ selectedChecks().length }} check{{ selectedChecks().length === 1 ? '' : 's' }} selected
                </p>
                <button
                  type="button"
                  class="msa-btn-primary"
                  [disabled]="startingScan() || !effectiveTargetId() || !selectedChecks().length || (selectedChecks().includes('pii') && !selectedPiiCategories().length)"
                  (click)="startScan()"
                >
                  @if (startingScan()) {
                    <msa-icon name="refresh" [size]="14" class="animate-spin" /> Starting scan
                  } @else {
                    <msa-icon name="shield" [size]="14" /> Run security scan
                  }
                </button>
              </div>
            </div>
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Detection coverage</h2>
                <p class="text-xs text-muted">What this scanner can and cannot tell you.</p>
              </div>
            </div>
            <ul class="divide-y divide-line">
              @for (check of checks(); track check.key) {
                <li class="px-5 py-3">
                  <p class="flex items-center gap-2 text-sm font-medium text-ink">
                    <msa-icon name="check-circle" [size]="14" class="text-brand" />
                    {{ check.label }}
                  </p>
                  <p class="mt-1 text-[11px] leading-relaxed text-slate-500">{{ check.limitation }}</p>
                </li>
              }
            </ul>
            <div class="border-t border-line bg-canvas/40 px-5 py-3">
              <p class="text-[10px] leading-relaxed text-slate-500">
                A clean scan is not evidence that a resource is secure. Attackers can encode,
                split or phrase content in ways these patterns do not detect.
              </p>
            </div>
          </section>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Findings by severity</h2>
                <p class="text-xs text-muted">Across all scans in this project.</p>
              </div>
              <span class="msa-badge bg-slate-50 text-slate-500">{{ data.findings }} total</span>
            </div>
            <div class="space-y-2.5 p-5">
              @for (severity of severityOrder; track severity) {
                <div class="flex items-center gap-3">
                  <span class="w-16 text-[11px] capitalize text-slate-500">{{ severity }}</span>
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
                <h2 class="msa-section-title">Security categories</h2>
                <p class="text-xs text-muted">What kinds of risks have been flagged.</p>
              </div>
            </div>
            @if (data.categories.length) {
              <ul class="divide-y divide-line">
                @for (category of data.categories; track category.category) {
                  <li class="flex items-center gap-3 px-5 py-2.5">
                    <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-soft text-brand">
                      <msa-icon name="shield" [size]="13" />
                    </span>
                    <span class="min-w-0 flex-1 font-mono text-[11px] text-slate-600">{{ category.category }}</span>
                    <span class="msa-badge bg-slate-50 text-slate-500">{{ category.count }}</span>
                  </li>
                }
              </ul>
            } @else {
              <p class="px-5 py-8 text-center text-sm text-muted">No findings yet. Run a scan to begin.</p>
            }
          </section>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Scan history</h2>
              <p class="text-xs text-muted">
                Previous scans are preserved so you can compare whether issues improved or reappeared.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">{{ scans().length }}</span>
          </div>

          @if (scans().length) {
            <div class="overflow-x-auto">
              <table class="w-full text-left text-sm">
                <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                  <tr>
                    <th class="px-5 py-2 font-semibold">Scan</th>
                    <th class="px-3 py-2 font-semibold">Status</th>
                    <th class="px-3 py-2 text-right font-semibold">Progress</th>
                    <th class="px-3 py-2 text-right font-semibold">Findings</th>
                    <th class="px-3 py-2 font-semibold">Started</th>
                    <th class="px-5 py-2 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  @for (scan of scans(); track scan.id) {
                    <tr class="cursor-pointer transition-colors hover:bg-canvas/60" [class.bg-brand-soft]="activeScan()?.id === scan.id" (click)="openScan(scan)">
                      <td class="px-5 py-3">
                        <p class="text-sm font-medium text-ink">{{ scan.target_label }}</p>
                        <p class="text-[11px] text-slate-400">
                          {{ scan.target_type }} · {{ scan.checks.join(', ') }} · {{ scan.created_at | date: 'medium' }}
                        </p>
                      </td>
                      <td class="px-3 py-3">
                        <span class="msa-badge" [class]="scanStatusClass(scan.status)">{{ scan.status }}</span>
                        @if (scan.highest_severity) {
                          <span class="msa-badge ml-1" [class]="severityClass(scan.highest_severity)">{{ scan.highest_severity }}</span>
                        }
                      </td>
                      <td class="px-3 py-3 text-right text-[11px] text-slate-500">
                        {{ scan.scanned_items }} / {{ scan.total_items }}
                        <span class="block text-[10px] text-slate-400">
                          {{ scanProgress(scan) }}%
                        </span>
                      </td>
                      <td class="px-3 py-3 text-right">
                        <span class="text-sm font-semibold text-ink">{{ scan.finding_count }}</span>
                      </td>
                      <td class="px-3 py-3 text-[11px] text-slate-500">
                        {{ (scan.started_at || scan.created_at) | date: 'short' }}
                      </td>
                      <td class="px-5 py-3 text-right">
                        <button
                          type="button"
                          class="msa-btn-ghost"
                          title="Rerun this scan configuration"
                          (click)="$event.stopPropagation(); rerunScan(scan)"
                        >
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
              No scans yet. Choose a target and run the first controlled scan above.
            </p>
          }
        </section>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Compare scans</h2>
              <p class="text-xs text-muted">
                See which detections are new, no longer present, or persisting between two scans of the same target.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">Review aid</span>
          </div>

          @if (scans().length < 2) {
            <p class="px-5 py-8 text-center text-sm text-muted">
              Run a scan twice to compare changes over time.
            </p>
          } @else {
            <div class="grid gap-3 border-b border-line bg-canvas/40 p-5 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Current scan (newer)</span>
                <select
                  class="msa-input"
                  [value]="compareCurrentId()"
                  (change)="setCompareCurrent($any($event.target).value)"
                  aria-label="Select current scan for comparison"
                >
                  @for (scan of scans(); track scan.id) {
                    <option [value]="scan.id">
                      {{ scan.target_label }} · {{ scan.created_at | date: 'short' }}
                    </option>
                  }
                </select>
              </label>
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Baseline scan (older)</span>
                <select
                  class="msa-input"
                  [value]="compareBaselineId()"
                  [disabled]="!compareBaselineOptions().length"
                  (change)="setCompareBaseline($any($event.target).value)"
                  aria-label="Select baseline scan for comparison"
                >
                  @if (!compareBaselineOptions().length) {
                    <option value="">No previous scan of this target</option>
                  }
                  @for (scan of compareBaselineOptions(); track scan.id) {
                    <option [value]="scan.id">
                      {{ scan.target_label }} · {{ scan.created_at | date: 'short' }}
                    </option>
                  }
                </select>
              </label>
              <button
                type="button"
                class="msa-btn-primary"
                [disabled]="comparing() || !compareBaselineId() || !compareCurrentId()"
                (click)="runComparison()"
              >
                @if (comparing()) {
                  <msa-icon name="refresh" [size]="14" class="animate-spin" /> Comparing
                } @else {
                  <msa-icon name="layers" [size]="14" /> Compare
                }
              </button>
            </div>

            @if (compareError()) {
              <p class="flex items-start gap-2 border-b border-rose-100 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
                <msa-icon name="alert" [size]="15" />
                <span>{{ compareError() }}</span>
              </p>
            }

            @if (comparison(); as cmp) {
              <div class="p-5">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p class="text-sm font-semibold text-ink">{{ cmp.target.label }}</p>
                    <p class="text-[11px] text-slate-400">
                      Baseline {{ cmp.baseline.created_at | date: 'medium' }} → current {{ cmp.current.created_at | date: 'medium' }}
                      @if (cmp.target.version_changed) {
                        · version {{ cmp.target.baseline_version || 'unknown' }} → {{ cmp.target.current_version || 'unknown' }}
                      }
                    </p>
                  </div>
                  <span class="msa-badge bg-slate-50 text-slate-500">
                    {{ cmp.checks.current.join(', ') }}
                  </span>
                </div>

                <div class="mt-4 grid gap-3 sm:grid-cols-4">
                  <div class="rounded-xl border border-amber-100 bg-amber-50/60 p-3">
                    <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-700">New</p>
                    <p class="mt-1 text-2xl font-semibold text-amber-800">{{ cmp.counts.new }}</p>
                    <p class="text-[10px] text-amber-700/70">Not detected in baseline</p>
                  </div>
                  <div class="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                    <p class="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">No longer detected</p>
                    <p class="mt-1 text-2xl font-semibold text-emerald-800">{{ cmp.counts.resolved }}</p>
                    <p class="text-[10px] text-emerald-700/70">Absence is not proof of a fix</p>
                  </div>
                  <div class="rounded-xl border border-sky-100 bg-sky-50/60 p-3">
                    <p class="text-[10px] font-semibold uppercase tracking-wide text-sky-700">Persisting</p>
                    <p class="mt-1 text-2xl font-semibold text-sky-800">{{ cmp.counts.persisting }}</p>
                    <p class="text-[10px] text-sky-700/70">Detected in both scans</p>
                  </div>
                  <div class="rounded-xl border border-line p-3">
                    <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Changed</p>
                    <p class="mt-1 text-2xl font-semibold text-ink">{{ cmp.counts.changed }}</p>
                    <p class="text-[10px] text-slate-400">Persisting findings with changed fields</p>
                  </div>
                </div>

                @for (warning of cmp.warnings; track warning) {
                  <p class="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-800">
                    <msa-icon name="alert" [size]="13" class="mt-0.5 shrink-0" />
                    <span>{{ warning }}</span>
                  </p>
                }

                <div class="mt-4 grid gap-3 lg:grid-cols-3">
                  <section class="overflow-hidden rounded-xl border border-line">
                    <div class="flex items-center justify-between bg-amber-50/60 px-3 py-2">
                      <h3 class="text-xs font-semibold text-amber-900">New findings</h3>
                      <span class="msa-badge bg-white text-amber-700">{{ cmp.counts.new }}</span>
                    </div>
                    <div class="divide-y divide-line">
                      @for (finding of cmp.new_findings; track finding.id) {
                        <button type="button" class="block w-full px-3 py-2.5 text-left transition-colors hover:bg-canvas/60" (click)="openFinding(finding)">
                          <span class="flex items-center gap-1.5">
                            <span class="msa-badge" [class]="severityClass(finding.severity)">{{ finding.severity }}</span>
                            <span class="truncate text-xs font-medium text-ink">{{ finding.title }}</span>
                          </span>
                          <span class="mt-1 block truncate text-[10px] text-slate-400">{{ finding.category }} · {{ finding.resource.label }}</span>
                        </button>
                      } @empty {
                        <p class="px-3 py-6 text-center text-[11px] text-muted">No new detections.</p>
                      }
                    </div>
                  </section>

                  <section class="overflow-hidden rounded-xl border border-line">
                    <div class="flex items-center justify-between bg-emerald-50/60 px-3 py-2">
                      <h3 class="text-xs font-semibold text-emerald-900">No longer detected</h3>
                      <span class="msa-badge bg-white text-emerald-700">{{ cmp.counts.resolved }}</span>
                    </div>
                    <div class="divide-y divide-line">
                      @for (finding of cmp.resolved_findings; track finding.id) {
                        <button type="button" class="block w-full px-3 py-2.5 text-left transition-colors hover:bg-canvas/60" (click)="openFinding(finding)">
                          <span class="flex items-center gap-1.5">
                            <span class="msa-badge" [class]="severityClass(finding.severity)">{{ finding.severity }}</span>
                            <span class="truncate text-xs font-medium text-ink">{{ finding.title }}</span>
                          </span>
                          <span class="mt-1 block truncate text-[10px] text-slate-400">{{ finding.category }} · {{ finding.resource.label }}</span>
                        </button>
                      } @empty {
                        <p class="px-3 py-6 text-center text-[11px] text-muted">Every baseline detection is still present.</p>
                      }
                    </div>
                  </section>

                  <section class="overflow-hidden rounded-xl border border-line">
                    <div class="flex items-center justify-between bg-sky-50/60 px-3 py-2">
                      <h3 class="text-xs font-semibold text-sky-900">Persisting</h3>
                      <span class="msa-badge bg-white text-sky-700">{{ cmp.counts.persisting }}</span>
                    </div>
                    <div class="divide-y divide-line">
                      @for (item of cmp.persisting; track item.current.id) {
                        <button type="button" class="block w-full px-3 py-2.5 text-left transition-colors hover:bg-canvas/60" (click)="openFinding(item.current)">
                          <span class="flex items-center gap-1.5">
                            <span class="msa-badge" [class]="severityClass(item.current.severity)">{{ item.current.severity }}</span>
                            <span class="truncate text-xs font-medium text-ink">{{ item.current.title }}</span>
                          </span>
                          <span class="mt-1 block truncate text-[10px] text-slate-400">{{ item.current.category }} · {{ item.current.resource.label }}</span>
                          <span class="mt-1 block text-[10px] text-slate-500">
                            {{ item.baseline.status }} → {{ item.current.status }} · {{ changedFields(item.changed_fields) }}
                          </span>
                        </button>
                      } @empty {
                        <p class="px-3 py-6 text-center text-[11px] text-muted">No detections persisted in both scans.</p>
                      }
                    </div>
                  </section>
                </div>
              </div>
            }
          }
        </section>

        @if (activeScan(); as scan) {
          <section class="msa-card mt-4 overflow-hidden">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Scan summary · {{ scan.target_label }}</h2>
                <p class="text-xs text-muted">
                  {{ scan.checks.join(', ') }} · {{ scan.status }} ·
                  {{ scan.created_at | date: 'medium' }}
                </p>
              </div>
              <button type="button" class="msa-btn-ghost" (click)="clearScan()">
                <msa-icon name="close" [size]="13" /> Show all findings
              </button>
            </div>
            <div class="grid gap-4 p-5 md:grid-cols-[1fr_1.3fr]">
              <div class="grid grid-cols-2 gap-3">
                <div class="rounded-lg border border-line p-3">
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Scanned</p>
                  <p class="mt-1 text-lg font-semibold text-ink">{{ scan.scanned_items }}/{{ scan.total_items }}</p>
                </div>
                <div class="rounded-lg border border-line p-3">
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Findings</p>
                  <p class="mt-1 text-lg font-semibold text-ink">{{ scan.finding_count }}</p>
                </div>
                <div class="rounded-lg border border-line p-3">
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Highest severity</p>
                  <p class="mt-1 text-sm font-semibold capitalize text-ink">{{ scan.highest_severity || 'None' }}</p>
                </div>
                <div class="rounded-lg border border-line p-3">
                  <p class="text-[10px] uppercase tracking-wide text-slate-400">Blocking labels</p>
                  <p class="mt-1 text-sm font-semibold text-ink">{{ scan.summary.disposition_counts['blocking'] || 0 }}</p>
                </div>
              </div>
              <div>
                <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Detection limitations</p>
                <ul class="mt-1.5 space-y-1 text-[11px] leading-relaxed text-slate-500">
                  @for (limitation of scan.summary.limitations; track limitation) {
                    <li class="flex items-start gap-1.5">
                      <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300"></span>
                      <span>{{ limitation }}</span>
                    </li>
                  }
                </ul>
                @if (scan.summary.truncated) {
                  <p class="mt-2 text-[11px] text-amber-700">
                    The target exceeded the configured scan cap; results cover only the first items.
                  </p>
                }
                @if (scan.blocking_enabled) {
                  <p class="mt-2 rounded-lg bg-rose-50 p-2 text-[11px] text-rose-700">
                    <strong>Blocking label opted in:</strong> {{ scan.blocking_reason }}
                    ({{ scan.blocking_severity }} and above). This scan did not interrupt execution.
                  </p>
                }
              </div>
            </div>
          </section>
        }

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header flex-wrap gap-2">
            <div>
              <h2 class="msa-section-title">Findings</h2>
              <p class="text-xs text-muted">
                @if (activeScan()) {
                  Showing findings from scan {{ shortId(activeScan()!.id) }}.
                } @else {
                  Review redacted evidence, rationale and recommended remediation.
                }
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <select class="msa-input text-xs" [value]="statusFilter()" (change)="setFindingFilter('status', $any($event.target).value)" aria-label="Filter findings by status">
                <option value="">Any status</option>
                <option value="open">Open</option>
                <option value="reviewed">Reviewed</option>
                <option value="resolved">Resolved</option>
              </select>
              <select class="msa-input text-xs" [value]="severityFilter()" (change)="setFindingFilter('severity', $any($event.target).value)" aria-label="Filter findings by severity">
                <option value="">Any severity</option>
                @for (severity of severityOrder; track severity) {
                  <option [value]="severity">{{ severity }}</option>
                }
              </select>
              <select class="msa-input max-w-[210px] text-xs" [value]="categoryFilter()" (change)="setFindingFilter('category', $any($event.target).value)" aria-label="Filter findings by category">
                <option value="">Any category</option>
                @for (category of data.categories; track category.category) {
                  <option [value]="category.category">{{ category.category }}</option>
                }
              </select>
              <button type="button" class="msa-btn-ghost" (click)="resetFindingFilters()">
                <msa-icon name="close" [size]="13" /> Reset
              </button>
            </div>
          </div>

          @if (findingsPage()?.results?.length) {
            <div class="overflow-x-auto">
              <table class="w-full text-left text-sm">
                <thead class="bg-canvas/60 text-[10px] uppercase tracking-wide text-slate-400">
                  <tr>
                    <th class="px-5 py-2 font-semibold">Finding</th>
                    <th class="px-3 py-2 font-semibold">Severity</th>
                    <th class="px-3 py-2 font-semibold">Disposition</th>
                    <th class="px-3 py-2 font-semibold">Resource</th>
                    <th class="px-3 py-2 font-semibold">Status</th>
                    <th class="px-5 py-2 text-right font-semibold">Detected</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  @for (finding of findingsPage()!.results; track finding.id) {
                    <tr class="cursor-pointer transition-colors hover:bg-canvas/60" (click)="openFinding(finding)">
                      <td class="px-5 py-3">
                        <p class="font-medium text-ink">{{ finding.title }}</p>
                        <p class="text-[11px] text-slate-400">{{ finding.category }} · {{ finding.rule_id }}</p>
                      </td>
                      <td class="px-3 py-3">
                        <span class="msa-badge" [class]="severityClass(finding.severity)">{{ finding.severity }}</span>
                      </td>
                      <td class="px-3 py-3">
                        <span class="msa-badge" [class]="dispositionClass(finding.disposition)">{{ finding.disposition }}</span>
                      </td>
                      <td class="max-w-[220px] px-3 py-3">
                        <p class="truncate text-xs text-slate-600">{{ finding.resource.label }}</p>
                        <p class="text-[10px] text-slate-400">{{ finding.resource.location }}</p>
                      </td>
                      <td class="px-3 py-3">
                        <span class="msa-badge" [class]="reviewStatusClass(finding.status)">{{ finding.status }}</span>
                      </td>
                      <td class="px-5 py-3 text-right text-[11px] text-slate-500">
                        {{ finding.detected_at | date: 'short' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="flex items-center justify-between border-t border-line px-5 py-3">
              <span class="text-[11px] text-slate-400">
                Page {{ findingsPageNumber() }} of {{ findingsTotalPages() }}
              </span>
              <div class="flex gap-2">
                <button type="button" class="msa-btn-ghost" [disabled]="!findingsPage()?.previous || loading()" (click)="goToFindingsPage(findingsPageNumber() - 1)">Previous</button>
                <button type="button" class="msa-btn-ghost" [disabled]="!findingsPage()?.next || loading()" (click)="goToFindingsPage(findingsPageNumber() + 1)">Next</button>
              </div>
            </div>
          } @else {
            <div class="p-10 text-center">
              <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-400">
                <msa-icon name="shield" [size]="22" />
              </span>
              <p class="mt-3 text-sm font-medium text-ink">No findings match</p>
              <p class="mt-1 text-xs text-muted">
                Run a scan or clear the filters. A clean result does not prove the resource is safe.
              </p>
            </div>
          }
        </section>
        }
      }
    </div>

    @if (selectedFinding(); as finding) {
      <msa-security-finding-detail
        [finding]="finding"
        (closed)="selectedFinding.set(null)"
        (updated)="findingUpdated($event)"
      />
    }
  `,
})
export class SecurityComponent implements OnInit, OnDestroy {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly datasetService = inject(DatasetService);
  private readonly playground = inject(PlaygroundService);
  private readonly security = inject(SecurityService);

  readonly targetTypes: { key: SecurityTargetType; label: string; icon: 'database' | 'sparkles' | 'play' }[] = [
    { key: 'dataset', label: 'Dataset', icon: 'database' },
    { key: 'prompt', label: 'Prompt', icon: 'sparkles' },
    { key: 'execution', label: 'Execution', icon: 'play' },
  ];
  readonly severityOrder: SecuritySeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

  readonly workspaces = signal<Workspace[]>([]);
  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly dashboard = signal<SecurityDashboard | null>(null);
  readonly scans = signal<SecurityScan[]>([]);
  readonly findingsPage = signal<Paginated<SecurityFinding> | null>(null);
  readonly findingsPageNumber = signal(1);
  readonly selectedFinding = signal<SecurityFinding | null>(null);
  readonly activeScan = signal<SecurityScan | null>(null);
  readonly comparison = signal<SecurityScanComparison | null>(null);
  readonly compareBaselineId = signal('');
  readonly compareCurrentId = signal('');
  readonly comparing = signal(false);
  readonly compareError = signal<string | null>(null);

  readonly catalog = signal<SecurityCheckCatalog | null>(null);
  readonly checks = computed(() => this.catalog()?.checks ?? []);
  readonly datasets = signal<Dataset[]>([]);
  readonly prompts = signal<SavedPrompt[]>([]);
  readonly executions = signal<Execution[]>([]);

  readonly targetType = signal<SecurityTargetType>('dataset');
  readonly targetId = signal('');
  readonly selectedChecks = signal<string[]>(['pii']);
  readonly selectedPiiCategories = signal<string[]>([]);
  readonly blockingEnabled = signal(false);
  readonly blockingSeverity = signal<SecuritySeverity>('high');
  readonly blockingReason = signal('');

  readonly statusFilter = signal('');
  readonly severityFilter = signal('');
  readonly categoryFilter = signal('');

  readonly loading = signal(true);
  readonly startingScan = signal(false);
  readonly error = signal<string | null>(null);
  readonly message = signal<string | null>(null);

  readonly targetOptions = computed<TargetOption[]>(() => {
    const type = this.targetType();
    if (type === 'prompt') {
      return this.prompts().map((prompt) => ({
        id: prompt.id,
        label: prompt.name,
        detail: prompt.current_version ? `v${prompt.current_version.version_number}` : 'no saved version',
      }));
    }
    if (type === 'execution') {
      return this.executions().map((execution) => ({
        id: execution.id,
        label: `Execution ${execution.id.slice(0, 8)}`,
        detail: `${execution.status} · ${execution.created_at}`,
      }));
    }
    return this.datasets().map((dataset) => ({
      id: dataset.id,
      label: dataset.name,
      detail: `${dataset.record_count} record${dataset.record_count === 1 ? '' : 's'} · v${dataset.version}`,
    }));
  });

  readonly effectiveTargetId = computed(
    () => this.targetId() || this.targetOptions()[0]?.id || '',
  );

  readonly compareBaselineOptions = computed(() => {
    const rows = this.scans();
    const current = rows.find((scan) => scan.id === this.compareCurrentId());
    if (!current) {
      return rows;
    }
    const currentTime = new Date(current.created_at).getTime();
    return rows.filter(
      (scan) =>
        scan.id !== current.id &&
        scan.target_type === current.target_type &&
        scan.target_identifier === current.target_identifier &&
        new Date(scan.created_at).getTime() <= currentTime,
    );
  });

  readonly findingsTotalPages = computed(() => {
    const page = this.findingsPage();
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
    this.activeScan.set(null);
    this.selectedFinding.set(null);
    this.statusFilter.set('');
    this.severityFilter.set('');
    this.categoryFilter.set('');
    this.findingsPageNumber.set(1);
    this.loadProjectData();
  }

  setTargetType(type: SecurityTargetType): void {
    this.targetType.set(type);
    this.targetId.set(this.targetOptions()[0]?.id ?? '');
  }

  toggleCheck(key: string): void {
    const current = this.selectedChecks();
    this.selectedChecks.set(
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  }

  togglePiiCategory(key: string): void {
    const current = this.selectedPiiCategories();
    this.selectedPiiCategories.set(
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  }

  startScan(): void {
    const projectId = this.selectedProjectId();
    const targetId = this.effectiveTargetId();
    const checks = this.selectedChecks();
    if (!projectId || !targetId || !checks.length) {
      this.error.set('Select a target and at least one check before running a scan.');
      return;
    }
    if (checks.includes('pii') && !this.selectedPiiCategories().length) {
      this.error.set('Select at least one PII category, or turn off the PII check.');
      return;
    }
    const config: Record<string, unknown> = {};
    if (checks.includes('pii')) {
      config['pii_categories'] = this.selectedPiiCategories();
    }
    this.startingScan.set(true);
    this.error.set(null);
    this.message.set(null);
    this.security
      .createScan(projectId, {
        target_type: this.targetType(),
        target_id: targetId,
        checks,
        config,
        blocking_enabled: this.blockingEnabled(),
        blocking_severity: this.blockingSeverity(),
        blocking_reason: this.blockingEnabled() ? this.blockingReason().trim() : '',
      })
      .subscribe({
        next: (scan) => {
          this.startingScan.set(false);
          this.activeScan.set(scan);
          this.compareCurrentId.set(scan.id);
          this.comparison.set(null);
          this.findingsPageNumber.set(1);
          this.message.set(
            scan.status === 'completed'
              ? `Scan completed: ${scan.finding_count} finding${scan.finding_count === 1 ? '' : 's'}.`
              : 'Scan queued. Progress will update automatically.',
          );
          this.loadData();
          if (scan.status === 'queued' || scan.status === 'running') {
            this.startPolling();
          }
        },
        error: (error: unknown) => {
          this.startingScan.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  refresh(): void {
    this.loadData();
  }

  setCompareCurrent(scanId: string): void {
    this.compareCurrentId.set(scanId);
    const options = this.compareBaselineOptions();
    this.compareBaselineId.set(options[0]?.id ?? '');
    this.comparison.set(null);
    this.compareError.set(null);
  }

  setCompareBaseline(scanId: string): void {
    this.compareBaselineId.set(scanId);
    this.comparison.set(null);
    this.compareError.set(null);
  }

  runComparison(): void {
    const projectId = this.selectedProjectId();
    const baseline = this.compareBaselineId();
    const current = this.compareCurrentId();
    if (!projectId || !baseline || !current || baseline === current) {
      this.compareError.set('Choose two different scans of the same target.');
      return;
    }
    this.comparing.set(true);
    this.compareError.set(null);
    this.security.comparison(projectId, baseline, current).subscribe({
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

  changedFields(fields: string[]): string {
    return fields.length ? fields.join(', ') : 'No field changes';
  }

  openScan(scan: SecurityScan): void {
    this.activeScan.set(scan);
    this.findingsPageNumber.set(1);
    this.loadFindings();
  }

  clearScan(): void {
    this.activeScan.set(null);
    this.findingsPageNumber.set(1);
    this.loadFindings();
  }

  rerunScan(scan: SecurityScan): void {
    this.error.set(null);
    this.security.rerun(scan.id).subscribe({
      next: (created) => {
        this.activeScan.set(created);
        this.compareCurrentId.set(created.id);
        this.comparison.set(null);
        this.message.set('Scan rerun started. The previous scan and findings were preserved.');
        this.findingsPageNumber.set(1);
        this.loadData();
        if (created.status === 'queued' || created.status === 'running') {
          this.startPolling();
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  openFinding(finding: SecurityFinding): void {
    this.selectedFinding.set(finding);
  }

  findingUpdated(finding: SecurityFinding): void {
    this.selectedFinding.set(finding);
    this.comparison.set(null);
    this.message.set(`Finding marked ${finding.status.replace('_', ' ')}. Detection history retained.`);
    this.loadData();
  }

  setFindingFilter(key: 'status' | 'severity' | 'category', value: string): void {
    if (key === 'status') {
      this.statusFilter.set(value);
    } else if (key === 'severity') {
      this.severityFilter.set(value);
    } else {
      this.categoryFilter.set(value);
    }
    this.findingsPageNumber.set(1);
    this.loadFindings();
  }

  resetFindingFilters(): void {
    this.statusFilter.set('');
    this.severityFilter.set('');
    this.categoryFilter.set('');
    this.findingsPageNumber.set(1);
    this.loadFindings();
  }

  goToFindingsPage(page: number): void {
    if (page < 1) {
      return;
    }
    this.findingsPageNumber.set(page);
    this.loadFindings();
  }

  targetTypeLabel(): string {
    return this.targetTypes.find((type) => type.key === this.targetType())?.label ?? 'Target';
  }

  scanProgress(scan: SecurityScan): number {
    if (!scan.total_items) {
      return scan.status === 'completed' ? 100 : 0;
    }
    return Math.min(100, Math.round((scan.scanned_items / scan.total_items) * 100));
  }

  severityShare(data: SecurityDashboard, severity: string): number {
    if (!data.findings) {
      return 0;
    }
    return Math.round(((data.severity_counts[severity] || 0) / data.findings) * 100);
  }

  severityBarClass(severity: string): string {
    if (severity === 'critical') {
      return 'bg-rose-500';
    }
    if (severity === 'high') {
      return 'bg-orange-400';
    }
    if (severity === 'medium') {
      return 'bg-amber-400';
    }
    if (severity === 'low') {
      return 'bg-sky-400';
    }
    return 'bg-slate-300';
  }

  severityClass(severity: string): string {
    if (severity === 'critical') {
      return 'bg-rose-100 text-rose-800';
    }
    if (severity === 'high') {
      return 'bg-orange-100 text-orange-800';
    }
    if (severity === 'medium') {
      return 'bg-amber-100 text-amber-800';
    }
    return 'bg-slate-100 text-slate-600';
  }

  dispositionClass(disposition: string): string {
    if (disposition === 'blocking') {
      return 'bg-rose-50 text-rose-700';
    }
    if (disposition === 'warning') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-slate-50 text-slate-500';
  }

  scanStatusClass(status: string): string {
    if (status === 'completed') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'failed') {
      return 'bg-rose-50 text-rose-700';
    }
    if (status === 'running') {
      return 'bg-sky-50 text-sky-700';
    }
    return 'bg-slate-50 text-slate-500';
  }

  reviewStatusClass(status: string): string {
    if (status === 'resolved') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'reviewed') {
      return 'bg-sky-50 text-sky-700';
    }
    return 'bg-amber-50 text-amber-700';
  }

  shortId(value: string): string {
    return value.slice(0, 8);
  }

  private loadCatalog(): void {
    this.security.catalog().subscribe({
      next: (catalog) => {
        this.catalog.set(catalog);
        this.selectedChecks.set(catalog.checks.map((check) => check.key));
        this.selectedPiiCategories.set(catalog.pii_categories.map((category) => category.key));
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
    this.loadTargets();
    this.loadData();
  }

  private loadTargets(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    forkJoin({
      datasets: this.datasetService.list(projectId).pipe(catchError(() => of([]))),
      prompts: this.playground.prompts(projectId).pipe(catchError(() => of([]))),
      executions: this.playground.executions(projectId).pipe(catchError(() => of([]))),
    }).subscribe({
      next: ({ datasets, prompts, executions }) => {
        this.datasets.set(datasets);
        this.prompts.set(prompts);
        this.executions.set(executions);
        const options = this.targetOptions();
        if (!options.some((option) => option.id === this.targetId())) {
          this.targetId.set(options[0]?.id ?? '');
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
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
      dashboard: this.security.dashboard(projectId),
      scans: this.security.scans(projectId),
      findings: this.findingsRequest(projectId),
    }).subscribe({
      next: ({ dashboard, scans, findings }) => {
        this.dashboard.set(dashboard);
        this.scans.set(scans);
        this.findingsPage.set(findings);
        this.ensureCompareDefaults();
        this.loading.set(false);
        if (!dashboard.running_scans) {
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

  private loadFindings(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    this.loading.set(true);
    this.findingsRequest(projectId).subscribe({
      next: (page) => {
        this.findingsPage.set(page);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private findingsRequest(projectId: string) {
    return this.security.findings(
      projectId,
      {
        status: this.statusFilter(),
        severity: this.severityFilter(),
        category: this.categoryFilter(),
        scan: this.activeScan()?.id ?? '',
      },
      this.findingsPageNumber(),
    );
  }

  private ensureCompareDefaults(): void {
    const rows = this.scans();
    if (!rows.length) {
      this.compareCurrentId.set('');
      this.compareBaselineId.set('');
      this.comparison.set(null);
      return;
    }
    const hasPrevious = (scan: SecurityScan) =>
      rows.some(
        (other) =>
          other.id !== scan.id &&
          other.target_type === scan.target_type &&
          other.target_identifier === scan.target_identifier &&
          new Date(other.created_at).getTime() <= new Date(scan.created_at).getTime(),
      );
    const selected = rows.find((scan) => scan.id === this.compareCurrentId());
    const current =
      (selected && hasPrevious(selected) ? selected : undefined) ??
      rows.find(hasPrevious) ??
      selected ??
      rows[0];
    this.compareCurrentId.set(current.id);
    const currentTime = new Date(current.created_at).getTime();
    const options = rows.filter(
      (scan) =>
        scan.id !== current.id &&
        scan.target_type === current.target_type &&
        scan.target_identifier === current.target_identifier &&
        new Date(scan.created_at).getTime() <= currentTime,
    );
    const baseline =
      options.find((scan) => scan.id === this.compareBaselineId()) ?? options[0];
    this.compareBaselineId.set(baseline?.id ?? '');
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandle = setInterval(() => this.loadData(), 2500);
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }
}
