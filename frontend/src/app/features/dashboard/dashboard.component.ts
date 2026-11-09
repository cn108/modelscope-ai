import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin, map, of, catchError } from 'rxjs';

import { ApiService } from '../../core/authentication/api.service';
import { AuthService } from '../../core/authentication/auth.service';
import { HealthResponse } from '../../shared/models/health.model';
import { Workspace } from '../../shared/models/workspace.model';
import { IconComponent, IconName } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from '../workspaces/workspace.service';

interface WorkspaceSummary {
  workspace: Workspace;
  projects: number;
  members: number;
}

interface StatCard {
  label: string;
  value: string;
  hint: string;
  icon: IconName;
  tile: string;
}

const TONES = {
  brand: 'bg-brand-soft text-brand',
  emerald: 'bg-emerald-50 text-emerald-600',
  violet: 'bg-violet-soft text-violet',
  amber: 'bg-amber-50 text-amber-600',
} as const;

@Component({
  selector: 'msa-dashboard',
  standalone: true,
  imports: [RouterLink, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Dashboard</h1>
          <p class="msa-sub">
            Welcome back{{ firstName() ? ', ' + firstName() : '' }}! Here's your
            ModelScope AI overview.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span
            class="msa-badge border"
            [class]="
              health()?.status === 'ok'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-amber-200 bg-amber-50 text-amber-700'
            "
          >
            <span
              class="h-1.5 w-1.5 rounded-full"
              [class]="
                health()?.status === 'ok' ? 'bg-emerald-500' : 'bg-amber-500'
              "
            ></span>
            {{ health() ? 'Platform ' + health()!.status : 'Checking status' }}
          </span>
          <button
            type="button"
            class="msa-btn-secondary"
            [disabled]="loading()"
            (click)="load()"
          >
            <msa-icon name="refresh" [size]="15" />
            Refresh
          </button>
        </div>
      </header>

      @if (error()) {
        <div
          class="msa-card mt-6 flex flex-wrap items-center gap-3 border-rose-200 bg-rose-50 p-4"
          role="alert"
        >
          <msa-icon name="alert" [size]="18" class="text-rose-600" />
          <div class="flex-1">
            <p class="text-sm font-medium text-rose-800">
              Something went wrong
            </p>
            <p class="text-xs text-rose-700">{{ error() }}</p>
          </div>
          <button type="button" class="msa-btn-secondary" (click)="load()">
            <msa-icon name="refresh" [size]="15" /> Try again
          </button>
        </div>
      }

      @if (loading()) {
        <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          @for (placeholder of [1, 2, 3, 4]; track placeholder) {
            <div class="msa-card p-5">
              <div class="msa-skeleton h-9 w-9"></div>
              <div class="msa-skeleton mt-4 h-3 w-24"></div>
              <div class="msa-skeleton mt-2 h-6 w-16"></div>
            </div>
          }
        </div>
        <p class="mt-6 text-sm text-muted">Loading your overview…</p>
      } @else {
        <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          @for (stat of stats(); track stat.label) {
            <article class="msa-card p-5">
              <div class="flex items-start justify-between">
                <span [class]="'msa-tile ' + stat.tile">
                  <msa-icon [name]="stat.icon" [size]="17" />
                </span>
                <span
                  class="rounded-full bg-slate-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400"
                >
                  Live
                </span>
              </div>
              <p class="mt-4 text-xs font-medium text-muted">{{ stat.label }}</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-ink">
                {{ stat.value }}
              </p>
              <p class="mt-1 text-[11px] text-slate-400">{{ stat.hint }}</p>
            </article>
          }
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <section class="msa-card">
            <div class="msa-card-header">
              <div>
                <h2 class="msa-section-title">Workspace breakdown</h2>
                <p class="text-xs text-muted">
                  Projects and people across the workspaces you belong to
                </p>
              </div>
              <a routerLink="/workspaces" class="msa-btn-ghost">
                View all <msa-icon name="arrow-right" [size]="14" />
              </a>
            </div>

            @if (summaries().length) {
              <ul class="space-y-4 p-5">
                @for (summary of summaries(); track summary.workspace.id) {
                  <li>
                    <div class="flex items-center gap-3">
                      <span
                        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-[11px] font-semibold text-brand"
                      >
                        {{ initialsFor(summary.workspace.name) }}
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium text-ink">
                          {{ summary.workspace.name }}
                        </span>
                        <span class="block text-[11px] text-slate-400">
                          {{ summary.projects }} project{{
                            summary.projects === 1 ? '' : 's'
                          }}
                          · {{ summary.members }} member{{
                            summary.members === 1 ? '' : 's'
                          }}
                          · {{ summary.workspace.role }}
                        </span>
                      </span>
                      <span class="text-xs font-medium text-slate-500">
                        {{ barPercent(summary) }}%
                      </span>
                    </div>
                    <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        class="h-full rounded-full bg-gradient-to-r from-brand to-violet transition-all"
                        [style.width.%]="barPercent(summary)"
                      ></div>
                    </div>
                  </li>
                }
              </ul>
            } @else {
              <div class="p-8 text-center">
                <span
                  class="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-400"
                >
                  <msa-icon name="layers" [size]="22" />
                </span>
                <p class="mt-3 text-sm font-medium text-ink">No data yet</p>
                <p class="mt-1 text-xs text-muted">
                  Create your first workspace to start tracking projects.
                </p>
                <a routerLink="/workspaces" class="msa-btn-primary mt-4">
                  <msa-icon name="plus" [size]="15" /> Create workspace
                </a>
              </div>
            }
          </section>

          <section class="msa-card">
            <div class="msa-card-header">
              <h2 class="msa-section-title">API status</h2>
              @if (health()) {
                <span class="msa-badge bg-slate-50 text-slate-500">health</span>
              }
            </div>

            @if (health(); as h) {
              <div class="space-y-4 p-5">
                <div class="flex items-center justify-between">
                  <span class="text-sm text-muted">Service</span>
                  <span class="text-sm font-medium text-ink">{{ h.service }}</span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-sm text-muted">Status</span>
                  <span
                    class="msa-badge"
                    [class]="
                      h.status === 'ok'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-amber-50 text-amber-700'
                    "
                  >
                    <span
                      class="h-1.5 w-1.5 rounded-full"
                      [class]="
                        h.status === 'ok' ? 'bg-emerald-500' : 'bg-amber-500'
                      "
                    ></span>
                    {{ h.status }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-sm text-muted">Database</span>
                  <span class="text-sm font-medium text-ink">
                    {{ h.database.engine ?? 'unknown' }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-sm text-muted">Database status</span>
                  <span class="text-sm font-medium text-ink">
                    {{ h.database.status }}
                  </span>
                </div>
                <div class="rounded-xl bg-canvas p-3 text-[11px] leading-relaxed text-slate-500">
                  Every request is authenticated with a short-lived token and
                  scoped to your workspace membership.
                </div>
              </div>
            } @else if (healthError()) {
              <div class="p-5">
                <p class="flex items-start gap-2 text-sm text-rose-700">
                  <msa-icon name="alert" [size]="16" />
                  <span>API unreachable: {{ healthError() }}</span>
                </p>
                <button
                  type="button"
                  class="msa-btn-secondary mt-3"
                  (click)="loadHealth()"
                >
                  <msa-icon name="refresh" [size]="15" /> Retry
                </button>
              </div>
            } @else {
              <p class="p-5 text-sm text-muted">Checking API…</p>
            }
          </section>
        </div>
      }
    </div>
  `,
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);

  readonly health = signal<HealthResponse | null>(null);
  readonly healthError = signal<string | null>(null);
  readonly summaries = signal<WorkspaceSummary[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly firstName = computed(() => {
    const source =
      this.auth.user()?.display_name?.trim() || this.auth.user()?.email || '';
    return source.split(/[\s@]/)[0] ?? '';
  });

  readonly totals = computed(() => {
    const summaries = this.summaries();
    return {
      workspaces: summaries.length,
      projects: summaries.reduce((sum, item) => sum + item.projects, 0),
      members: summaries.reduce((sum, item) => sum + item.members, 0),
    };
  });

  readonly stats = computed<StatCard[]>(() => {
    const totals = this.totals();
    return [
      {
        label: 'Workspaces',
        value: String(totals.workspaces),
        hint: 'Teams you can access',
        icon: 'layers',
        tile: TONES.brand,
      },
      {
        label: 'Projects',
        value: String(totals.projects),
        hint: 'Across every workspace',
        icon: 'folder',
        tile: TONES.violet,
      },
      {
        label: 'Team members',
        value: String(totals.members),
        hint: 'Including your own membership',
        icon: 'users',
        tile: TONES.emerald,
      },
      {
        label: 'API status',
        value: this.health()?.status ?? (this.healthError() ? 'down' : '…'),
        hint: this.health()?.database.engine
          ? 'Database: ' + this.health()!.database.engine
          : 'Checking the platform',
        icon: 'server',
        tile: TONES.amber,
      },
    ];
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.loadHealth();

    this.workspaceService.list().subscribe({
      next: (page) => {
        if (!page.results.length) {
          this.summaries.set([]);
          this.loading.set(false);
          return;
        }
        forkJoin(
          page.results.map((workspace) =>
            forkJoin({
              projects: this.projectService
                .list(workspace.id)
                .pipe(catchError(() => of(null))),
              members: this.workspaceService
                .members(workspace.id)
                .pipe(catchError(() => of(null))),
            }).pipe(
              map((result) => ({
                workspace,
                projects: result.projects?.count ?? 0,
                members: result.members?.count ?? 0,
              })),
            ),
          ),
        ).subscribe({
          next: (summaries) => {
            this.summaries.set(summaries);
            this.loading.set(false);
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Could not load your workspaces.');
          },
        });
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof Error
            ? error.message
            : 'Could not load your workspaces.',
        );
      },
    });
  }

  loadHealth(): void {
    this.healthError.set(null);
    this.api.getHealth().subscribe({
      next: (h) => this.health.set(h),
      error: (err: { message?: string }) =>
        this.healthError.set(err.message ?? 'unknown error'),
    });
  }

  barPercent(summary: WorkspaceSummary): number {
    const max = Math.max(...this.summaries().map((item) => item.projects), 1);
    return Math.round((summary.projects / max) * 100);
  }

  initialsFor(name: string): string {
    return name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase();
  }
}
