import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { ProviderConfig, ProviderService } from '../providers/provider.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  Execution,
  ExecutionInput,
  ExecutionResult,
  PlaygroundService,
  PromptVersion,
  SavedPrompt,
} from './playground.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

type Slot = 'a' | 'b';

@Component({
  selector: 'msa-playground',
  standalone: true,
  imports: [DatePipe, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Playground</h1>
          <p class="msa-sub">
            Test a model or compare two on the same prompts. Every run is saved
            with its exact inputs.
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

      @if (loading()) {
        <div class="mt-6 grid gap-4 xl:grid-cols-[1.7fr_1fr]">
          <div class="msa-card p-5">
            <div class="msa-skeleton h-3 w-40"></div>
            <div class="msa-skeleton mt-4 h-24 w-full"></div>
            <div class="msa-skeleton mt-3 h-24 w-full"></div>
          </div>
          <div class="msa-card p-5">
            <div class="msa-skeleton h-3 w-32"></div>
            <div class="msa-skeleton mt-4 h-10 w-full"></div>
          </div>
        </div>
      } @else if (!projects().length) {
        <div class="msa-card mt-6 flex flex-col items-center p-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand">
            <msa-icon name="play" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            The playground runs against providers configured on a project.
            Create a project in Workspaces, then add a provider.
          </p>
        </div>
      } @else {
        <div class="mt-6 grid gap-4 xl:grid-cols-[1.7fr_1fr]">
          <div class="space-y-4">
            <section class="msa-card p-5">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="inline-flex rounded-lg border border-line bg-canvas p-1">
                  @for (option of modes; track option.value) {
                    <button
                      type="button"
                      class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
                      [class]="
                        mode() === option.value
                          ? 'bg-white text-ink shadow-sm'
                          : 'text-muted hover:text-ink'
                      "
                      (click)="setMode(option.value)"
                    >
                      {{ option.label }}
                    </button>
                  }
                </div>
                @if (editingPrompt(); as prompt) {
                  <span class="msa-badge bg-brand-soft text-brand">
                    <msa-icon name="sparkles" [size]="12" />
                    {{ prompt.name }}
                    @if (prompt.current_version) {
                      · v{{ prompt.current_version.version_number }}
                    }
                  </span>
                }
              </div>

              @if (!providers().length) {
                <p class="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                  This project has no providers yet. Add a Z.ai or Ollama
                  provider in Workspaces before running a model.
                </p>
              }

              <div class="mt-4 space-y-3">
                <div>
                  <label class="msa-label" for="system-prompt">System prompt</label>
                  <textarea
                    id="system-prompt"
                    rows="2"
                    class="msa-input resize-y"
                    placeholder="Optional instructions that shape the model's behaviour"
                    [value]="systemPrompt()"
                    (input)="systemPrompt.set($any($event.target).value)"
                  ></textarea>
                </div>
                <div>
                  <label class="msa-label" for="user-prompt">User prompt</label>
                  <textarea
                    id="user-prompt"
                    rows="4"
                    class="msa-input resize-y"
                    placeholder="The input both models will receive"
                    [value]="userPrompt()"
                    (input)="userPrompt.set($any($event.target).value)"
                  ></textarea>
                </div>
              </div>

              <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <label class="msa-label" for="temperature">Temperature</label>
                  <input
                    id="temperature"
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    class="msa-input"
                    placeholder="Provider default"
                    [value]="temperature()"
                    (input)="temperature.set($any($event.target).value)"
                  />
                </div>
                <div>
                  <label class="msa-label" for="max-tokens">Max tokens</label>
                  <input
                    id="max-tokens"
                    type="number"
                    min="1"
                    step="1"
                    class="msa-input"
                    placeholder="Provider default"
                    [value]="maxTokens()"
                    (input)="maxTokens.set($any($event.target).value)"
                  />
                </div>
              </div>

              <div class="mt-4 grid gap-3" [class]="mode() === 'compare' ? 'sm:grid-cols-2' : ''">
                <div class="rounded-xl border border-line bg-canvas/50 p-3">
                  <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Model A
                  </p>
                  <div class="mt-2 space-y-2">
                    <select
                      class="msa-input"
                      [value]="modelAProvider()"
                      (change)="setProvider('a', $any($event.target).value)"
                      aria-label="Provider for model A"
                    >
                      @for (provider of providers(); track provider.id) {
                        <option [value]="provider.id">{{ provider.name }}</option>
                      }
                    </select>
                    <input
                      class="msa-input"
                      list="model-a-options"
                      placeholder="Model id, e.g. glm-5.3"
                      aria-label="Model id for model A"
                      [value]="modelAModel()"
                      (input)="modelAModel.set($any($event.target).value)"
                    />
                    <datalist id="model-a-options">
                      @for (model of modelsFor(modelAProvider()); track model.model_id) {
                        <option [value]="model.model_id">{{ model.display_name }}</option>
                      }
                    </datalist>
                  </div>
                </div>

                @if (mode() === 'compare') {
                  <div class="rounded-xl border border-line bg-canvas/50 p-3">
                    <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Model B
                    </p>
                    <div class="mt-2 space-y-2">
                      <select
                        class="msa-input"
                        [value]="modelBProvider()"
                        (change)="setProvider('b', $any($event.target).value)"
                        aria-label="Provider for model B"
                      >
                        @for (provider of providers(); track provider.id) {
                          <option [value]="provider.id">{{ provider.name }}</option>
                        }
                      </select>
                      <input
                        class="msa-input"
                        list="model-b-options"
                        placeholder="Model id, e.g. llama3.2"
                        aria-label="Model id for model B"
                        [value]="modelBModel()"
                        (input)="modelBModel.set($any($event.target).value)"
                      />
                      <datalist id="model-b-options">
                        @for (model of modelsFor(modelBProvider()); track model.model_id) {
                          <option [value]="model.model_id">{{ model.display_name }}</option>
                        }
                      </datalist>
                    </div>
                  </div>
                }
              </div>

              <div class="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  class="msa-btn-primary"
                  [disabled]="running() || !providers().length"
                  (click)="run()"
                >
                  <msa-icon [name]="running() ? 'refresh' : 'play'" [size]="15" />
                  {{ running() ? 'Running…' : mode() === 'compare' ? 'Run comparison' : 'Run model' }}
                </button>
                @if (currentExecution(); as execution) {
                  <button
                    type="button"
                    class="msa-btn-secondary"
                    [disabled]="running()"
                    (click)="rerun(execution)"
                  >
                    <msa-icon name="refresh" [size]="15" /> Rerun
                  </button>
                  @if (execution.prompt_version) {
                    <span class="text-xs text-muted">
                      Snapshot of prompt v{{ execution.prompt_version }}
                    </span>
                  }
                }
              </div>
            </section>

            @if (currentExecution(); as execution) {
              <section class="msa-card overflow-hidden">
                <div class="msa-card-header">
                  <div>
                    <h2 class="msa-section-title">
                      {{ execution.mode === 'compare' ? 'Comparison' : 'Response' }}
                    </h2>
                    <p class="text-xs text-muted">
                      {{ execution.created_at | date: 'medium' }} ·
                      {{ execution.results.length }} model{{
                        execution.results.length === 1 ? '' : 's'
                      }}
                    </p>
                  </div>
                  <span class="msa-badge" [class]="statusClass(execution.status)">
                    {{ execution.status }}
                  </span>
                </div>

                <div
                  class="grid gap-3 p-4"
                  [class]="execution.results.length > 1 ? 'lg:grid-cols-2' : ''"
                >
                  @for (result of execution.results; track result.id) {
                    <article class="rounded-xl border border-line bg-canvas/30 p-4">
                      <div class="flex flex-wrap items-center justify-between gap-2">
                        <div class="min-w-0">
                          <p class="truncate text-sm font-semibold text-ink">
                            {{ result.provider_name }}
                          </p>
                          <p class="truncate text-[11px] text-slate-400">
                            {{ result.model_id }} · {{ result.provider_kind }}
                          </p>
                        </div>
                        <span class="msa-badge" [class]="statusClass(result.status)">
                          {{ result.status }}
                        </span>
                      </div>

                      @if (result.status === 'failed') {
                        <p class="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
                          {{ result.error?.message || 'The model did not return a response.' }}
                        </p>
                      } @else {
                        <p class="mt-3 whitespace-pre-wrap break-words text-sm text-slate-700">
                          {{ result.content || 'The model returned an empty response.' }}
                        </p>
                      }

                      <dl class="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center">
                        <div>
                          <dt class="text-[10px] uppercase tracking-wide text-slate-400">Time</dt>
                          <dd class="text-sm font-medium text-ink">{{ latency(result) }}</dd>
                        </div>
                        <div>
                          <dt class="text-[10px] uppercase tracking-wide text-slate-400">Tokens</dt>
                          <dd class="text-sm font-medium text-ink">{{ tokens(result) }}</dd>
                        </div>
                        <div>
                          <dt class="text-[10px] uppercase tracking-wide text-slate-400">Cost</dt>
                          <dd class="text-sm font-medium text-ink">{{ cost(result) }}</dd>
                        </div>
                      </dl>
                      @if (!result.tokens_are_provider_reported && result.status === 'succeeded') {
                        <p class="mt-2 text-[11px] text-slate-400">
                          Token counts were not reported by this provider.
                        </p>
                      }
                    </article>
                  }
                </div>
              </section>
            }

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">History</h2>
                  <p class="text-xs text-muted">
                    Saved runs keep their original prompts and settings.
                  </p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ executions().length }}
                </span>
              </div>

              @if (executions().length) {
                <ul class="divide-y divide-line">
                  @for (execution of executions(); track execution.id) {
                    <li
                      class="flex flex-wrap items-center gap-3 px-5 py-3"
                      [class]="
                        currentExecution()?.id === execution.id ? 'bg-brand-soft/40' : ''
                      "
                    >
                      <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-slate-400 ring-1 ring-line">
                        <msa-icon name="clock" [size]="15" />
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium text-ink">
                          {{ execution.user_prompt }}
                        </span>
                        <span class="block truncate text-[11px] text-slate-400">
                          {{ execution.created_at | date: 'medium' }} ·
                          {{ modelSummary(execution) }}
                        </span>
                      </span>
                      <span class="msa-badge" [class]="statusClass(execution.status)">
                        {{ execution.status }}
                      </span>
                      <button
                        type="button"
                        class="msa-btn-ghost"
                        (click)="openExecution(execution)"
                      >
                        View
                      </button>
                      <button
                        type="button"
                        class="msa-btn-ghost"
                        [disabled]="running()"
                        (click)="rerun(execution)"
                      >
                        <msa-icon name="refresh" [size]="13" /> Rerun
                      </button>
                    </li>
                  }
                </ul>
              } @else {
                <p class="px-5 py-8 text-center text-sm text-muted">
                  No runs yet. Execute a model to start your history.
                </p>
              }
            </section>
          </div>

          <div class="space-y-4">
            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h2 class="msa-section-title">Saved prompts</h2>
                  <p class="text-xs text-muted">Reusable prompts with versions.</p>
                </div>
                <msa-icon name="sparkles" [size]="17" />
              </div>

              <div class="border-b border-line p-4">
                <label class="msa-label" for="prompt-name">Save current draft</label>
                <div class="flex gap-2">
                  <input
                    id="prompt-name"
                    class="msa-input"
                    placeholder="Prompt name"
                    [value]="newPromptName()"
                    (input)="newPromptName.set($any($event.target).value)"
                  />
                  @if (editingPrompt(); as prompt) {
                    <button
                      type="button"
                      class="msa-btn-secondary whitespace-nowrap"
                      [disabled]="savingPrompt()"
                      (click)="saveNewVersion(prompt)"
                    >
                      Save v{{ (prompt.current_version?.version_number ?? 0) + 1 }}
                    </button>
                  } @else {
                    <button
                      type="button"
                      class="msa-btn-primary whitespace-nowrap"
                      [disabled]="savingPrompt()"
                      (click)="createPrompt()"
                    >
                      Save
                    </button>
                  }
                </div>
                @if (editingPrompt()) {
                  <button type="button" class="msa-btn-ghost mt-2" (click)="clearEditing()">
                    <msa-icon name="close" [size]="13" /> Stop editing saved prompt
                  </button>
                }
              </div>

              @if (prompts().length) {
                <ul class="divide-y divide-line">
                  @for (prompt of prompts(); track prompt.id) {
                    <li class="px-4 py-3">
                      <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                          <p class="truncate text-sm font-medium text-ink">{{ prompt.name }}</p>
                          <p class="text-[11px] text-slate-400">
                            {{ prompt.version_count }} version{{
                              prompt.version_count === 1 ? '' : 's'
                            }}
                            @if (prompt.current_version) {
                              · v{{ prompt.current_version.version_number }}
                            }
                          </p>
                        </div>
                        <div class="flex shrink-0 gap-1">
                          <button
                            type="button"
                            class="msa-icon-btn"
                            title="Use this prompt"
                            (click)="usePrompt(prompt)"
                          >
                            <msa-icon name="play" [size]="14" />
                          </button>
                          <button
                            type="button"
                            class="msa-icon-btn"
                            title="History"
                            (click)="toggleVersions(prompt)"
                          >
                            <msa-icon name="clock" [size]="14" />
                          </button>
                          <button
                            type="button"
                            class="msa-icon-btn"
                            title="Duplicate"
                            (click)="duplicatePrompt(prompt)"
                          >
                            <msa-icon name="copy" [size]="14" />
                          </button>
                          <button
                            type="button"
                            class="msa-icon-btn text-rose-600"
                            title="Delete prompt"
                            (click)="deletePrompt(prompt)"
                          >
                            <msa-icon name="trash" [size]="14" />
                          </button>
                        </div>
                      </div>

                      @if (openPromptId() === prompt.id) {
                        <div class="mt-3 rounded-lg border border-line bg-canvas/40 p-3">
                          <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                            Version history
                          </p>
                          @if (versions().length) {
                            <ul class="mt-2 space-y-2">
                              @for (version of versions(); track version.id) {
                                <li class="rounded-lg bg-white p-2 ring-1 ring-line">
                                  <div class="flex items-center justify-between gap-2">
                                    <span class="text-xs font-semibold text-ink">
                                      v{{ version.version_number }}
                                    </span>
                                    <span class="text-[10px] text-slate-400">
                                      {{ version.created_at | date: 'short' }}
                                    </span>
                                  </div>
                                  <p class="mt-1 line-clamp-3 whitespace-pre-wrap text-[11px] text-slate-500">
                                    {{ version.user_prompt }}
                                  </p>
                                  <button
                                    type="button"
                                    class="msa-btn-ghost mt-1"
                                    [disabled]="savingPrompt()"
                                    (click)="restore(prompt, version)"
                                  >
                                    <msa-icon name="refresh" [size]="12" />
                                    Restore v{{ version.version_number }}
                                  </button>
                                </li>
                              }
                            </ul>
                          } @else {
                            <p class="mt-2 text-xs text-muted">No versions yet.</p>
                          }
                        </div>
                      }
                    </li>
                  }
                </ul>
              } @else {
                <p class="px-4 py-8 text-center text-sm text-muted">
                  No saved prompts. Write a draft and save it for reuse.
                </p>
              }
            </section>

            <section class="msa-card p-4">
              <h2 class="msa-section-title">Metrics</h2>
              <p class="mt-1 text-xs text-muted">
                Latency and token usage come from the provider. Cost is shown
                only when the provider reports pricing.
              </p>
            </section>
          </div>
        </div>
      }
    </div>
  `,
})
export class PlaygroundComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly providerService = inject(ProviderService);
  private readonly playground = inject(PlaygroundService);

  readonly modes = [
    { value: 'single' as const, label: 'Single model' },
    { value: 'compare' as const, label: 'Compare two' },
  ];

  readonly workspaces = signal<Workspace[]>([]);
  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly providers = signal<ProviderConfig[]>([]);
  readonly prompts = signal<SavedPrompt[]>([]);
  readonly executions = signal<Execution[]>([]);
  readonly versions = signal<PromptVersion[]>([]);
  readonly openPromptId = signal<string | null>(null);
  readonly currentExecution = signal<Execution | null>(null);
  readonly editingPrompt = signal<SavedPrompt | null>(null);

  readonly loading = signal(true);
  readonly running = signal(false);
  readonly savingPrompt = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  readonly mode = signal<'single' | 'compare'>('single');
  readonly systemPrompt = signal('');
  readonly userPrompt = signal('');
  readonly temperature = signal('');
  readonly maxTokens = signal('');
  readonly newPromptName = signal('');
  readonly modelAProvider = signal('');
  readonly modelAModel = signal('');
  readonly modelBProvider = signal('');
  readonly modelBModel = signal('');

  readonly selectedProject = computed(
    () => this.projects().find((project) => project.id === this.selectedProjectId()) ?? null,
  );

  ngOnInit(): void {
    this.loadProjects();
  }

  modelsFor(providerId: string): { model_id: string; display_name: string }[] {
    return this.providers().find((provider) => provider.id === providerId)?.models ?? [];
  }

  setMode(value: 'single' | 'compare'): void {
    this.mode.set(value);
    if (value === 'single') {
      this.modelBProvider.set('');
      this.modelBModel.set('');
    } else if (!this.modelBProvider()) {
      this.modelBProvider.set(this.providers()[0]?.id ?? '');
    }
  }

  setProvider(slot: Slot, providerId: string): void {
    if (slot === 'a') {
      this.modelAProvider.set(providerId);
    } else {
      this.modelBProvider.set(providerId);
    }
  }

  selectProject(projectId: string): void {
    if (!projectId || projectId === this.selectedProjectId()) {
      return;
    }
    this.selectedProjectId.set(projectId);
    this.resetDraft();
    this.loadProjectData(projectId);
  }

  run(): void {
    const projectId = this.selectedProjectId();
    if (!projectId) {
      return;
    }
    if (!this.userPrompt().trim()) {
      this.error.set('Enter a user prompt before running.');
      return;
    }
    const models = this.buildModels();
    if (!models) {
      return;
    }
    const payload: ExecutionInput = {
      system_prompt: this.systemPrompt(),
      user_prompt: this.userPrompt(),
      parameters: this.buildParameters(),
      prompt: this.editingPrompt()?.id ?? null,
      models,
    };
    this.running.set(true);
    this.error.set(null);
    this.notice.set(null);
    this.playground.run(projectId, payload).subscribe({
      next: (execution) => {
        this.running.set(false);
        this.currentExecution.set(execution);
        this.executions.update((rows) => [execution, ...rows]);
        this.notice.set(
          execution.status === 'partial'
            ? 'One model failed; the other response was saved.'
            : execution.status === 'failed'
              ? 'The run finished but every model failed. See the details.'
              : 'Run saved to history.',
        );
      },
      error: (error: unknown) => {
        this.running.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  rerun(execution: Execution): void {
    this.running.set(true);
    this.error.set(null);
    this.notice.set(null);
    this.playground.rerun(execution.id).subscribe({
      next: (created) => {
        this.running.set(false);
        this.currentExecution.set(created);
        this.executions.update((rows) => [created, ...rows]);
        this.notice.set('Rerun saved as a new execution.');
      },
      error: (error: unknown) => {
        this.running.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  openExecution(execution: Execution): void {
    this.currentExecution.set(execution);
    this.systemPrompt.set(execution.system_prompt);
    this.userPrompt.set(execution.user_prompt);
    this.applyParameters(execution.parameters);
    this.mode.set(execution.mode);
    const [first, second] = execution.results;
    if (first?.provider) {
      this.modelAProvider.set(first.provider);
      this.modelAModel.set(first.model_id);
    }
    if (second?.provider) {
      this.modelBProvider.set(second.provider);
      this.modelBModel.set(second.model_id);
    } else {
      this.modelBProvider.set('');
      this.modelBModel.set('');
    }
  }

  createPrompt(): void {
    const projectId = this.selectedProjectId();
    const name = this.newPromptName().trim();
    if (!projectId) {
      return;
    }
    if (!name) {
      this.error.set('Give the prompt a name before saving.');
      return;
    }
    if (!this.userPrompt().trim()) {
      this.error.set('Enter a user prompt before saving.');
      return;
    }
    this.savingPrompt.set(true);
    this.error.set(null);
    this.playground
      .createPrompt(projectId, {
        name,
        system_prompt: this.systemPrompt(),
        user_prompt: this.userPrompt(),
        parameters: this.buildParameters(),
      })
      .subscribe({
        next: (prompt) => {
          this.savingPrompt.set(false);
          this.newPromptName.set('');
          this.prompts.update((rows) => [...rows, prompt].sort((a, b) => a.name.localeCompare(b.name)));
          this.editingPrompt.set(prompt);
          this.notice.set(`Saved prompt “${prompt.name}”.`);
        },
        error: (error: unknown) => {
          this.savingPrompt.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  saveNewVersion(prompt: SavedPrompt): void {
    if (!this.userPrompt().trim()) {
      this.error.set('Enter a user prompt before saving a new version.');
      return;
    }
    this.savingPrompt.set(true);
    this.error.set(null);
    this.playground
      .updatePrompt(prompt.id, {
        system_prompt: this.systemPrompt(),
        user_prompt: this.userPrompt(),
        parameters: this.buildParameters(),
      })
      .subscribe({
        next: (updated) => {
          this.savingPrompt.set(false);
          this.editingPrompt.set(updated);
          this.replacePrompt(updated);
          if (this.openPromptId() === updated.id) {
            this.loadVersions(updated.id);
          }
          this.notice.set(
            `Saved v${updated.current_version?.version_number ?? updated.version_count} of “${updated.name}”.`,
          );
        },
        error: (error: unknown) => {
          this.savingPrompt.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  usePrompt(prompt: SavedPrompt): void {
    this.editingPrompt.set(prompt);
    this.newPromptName.set(prompt.name);
    const version = prompt.current_version;
    if (version) {
      this.systemPrompt.set(version.system_prompt);
      this.userPrompt.set(version.user_prompt);
      this.applyParameters(version.parameters);
    }
    this.notice.set(`Loaded “${prompt.name}”. Running will reference this prompt.`);
  }

  toggleVersions(prompt: SavedPrompt): void {
    if (this.openPromptId() === prompt.id) {
      this.openPromptId.set(null);
      return;
    }
    this.openPromptId.set(prompt.id);
    this.loadVersions(prompt.id);
  }

  restore(prompt: SavedPrompt, version: PromptVersion): void {
    this.savingPrompt.set(true);
    this.error.set(null);
    this.playground.restore(prompt.id, version.version_number).subscribe({
      next: (updated) => {
        this.savingPrompt.set(false);
        this.replacePrompt(updated);
        this.editingPrompt.set(updated);
        if (updated.current_version) {
          this.systemPrompt.set(updated.current_version.system_prompt);
          this.userPrompt.set(updated.current_version.user_prompt);
          this.applyParameters(updated.current_version.parameters);
        }
        this.loadVersions(updated.id);
        this.notice.set(
          `Restored v${version.version_number} as v${updated.current_version?.version_number}.`,
        );
      },
      error: (error: unknown) => {
        this.savingPrompt.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  duplicatePrompt(prompt: SavedPrompt): void {
    this.playground.duplicatePrompt(prompt.id).subscribe({
      next: (copy) => {
        this.prompts.update((rows) =>
          [...rows, copy].sort((a, b) => a.name.localeCompare(b.name)),
        );
        this.notice.set(`Duplicated as “${copy.name}”.`);
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  deletePrompt(prompt: SavedPrompt): void {
    if (!globalThis.confirm(`Delete the saved prompt “${prompt.name}”?`)) {
      return;
    }
    this.playground.deletePrompt(prompt.id).subscribe({
      next: () => {
        this.prompts.update((rows) => rows.filter((row) => row.id !== prompt.id));
        if (this.editingPrompt()?.id === prompt.id) {
          this.editingPrompt.set(null);
        }
        this.notice.set('Saved prompt deleted. Past runs keep their snapshots.');
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  clearEditing(): void {
    this.editingPrompt.set(null);
    this.newPromptName.set('');
  }

  latency(result: ExecutionResult): string {
    if (result.latency_ms === null) {
      return '—';
    }
    return result.latency_ms >= 1000
      ? `${(result.latency_ms / 1000).toFixed(2)} s`
      : `${Math.round(result.latency_ms)} ms`;
  }

  tokens(result: ExecutionResult): string {
    if (result.input_tokens === null && result.output_tokens === null) {
      return 'Not reported';
    }
    return `${result.input_tokens ?? '?'} in / ${result.output_tokens ?? '?'} out`;
  }

  cost(result: ExecutionResult): string {
    if (result.estimated_cost === null) {
      return 'Not reported';
    }
    return `${result.estimated_cost} ${result.cost_currency}`.trim();
  }

  modelSummary(execution: Execution): string {
    return execution.results.map((result) => result.model_id).join(' vs ');
  }

  statusClass(status: string): string {
    if (status === 'succeeded') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (status === 'partial') {
      return 'bg-amber-50 text-amber-700';
    }
    return 'bg-rose-50 text-rose-700';
  }

  private loadProjects(): void {
    this.loading.set(true);
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
      providers: this.providerService.list(projectId).pipe(catchError(() => of([]))),
      prompts: this.playground.prompts(projectId).pipe(catchError(() => of([]))),
      executions: this.playground.executions(projectId).pipe(catchError(() => of([]))),
    }).subscribe({
      next: ({ providers, prompts, executions }) => {
        this.providers.set(providers);
        this.prompts.set(prompts);
        this.executions.set(executions);
        const firstProvider = providers[0]?.id ?? '';
        this.modelAProvider.set(firstProvider);
        this.modelBProvider.set(this.mode() === 'compare' ? firstProvider : '');
        const firstModel = providers[0]?.models[0]?.model_id ?? '';
        this.modelAModel.set(firstModel);
        this.modelBModel.set('');
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private loadVersions(promptId: string): void {
    this.playground.versions(promptId).subscribe({
      next: (versions) => this.versions.set(versions),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private replacePrompt(updated: SavedPrompt): void {
    this.prompts.update((rows) =>
      rows
        .map((row) => (row.id === updated.id ? updated : row))
        .sort((a, b) => a.name.localeCompare(b.name)),
    );
  }

  private resetDraft(): void {
    this.currentExecution.set(null);
    this.editingPrompt.set(null);
    this.openPromptId.set(null);
    this.versions.set([]);
    this.notice.set(null);
    this.error.set(null);
    this.newPromptName.set('');
  }

  private applyParameters(parameters: Record<string, unknown>): void {
    const temperature = parameters['temperature'];
    const maxTokens = parameters['max_tokens'];
    this.temperature.set(
      typeof temperature === 'number' ? String(temperature) : '',
    );
    this.maxTokens.set(typeof maxTokens === 'number' ? String(maxTokens) : '');
  }

  private buildParameters(): Record<string, unknown> {
    const parameters: Record<string, unknown> = {};
    const temperature = Number.parseFloat(this.temperature());
    if (!Number.isNaN(temperature)) {
      parameters['temperature'] = temperature;
    }
    const maxTokens = Number.parseInt(this.maxTokens(), 10);
    if (!Number.isNaN(maxTokens)) {
      parameters['max_tokens'] = maxTokens;
    }
    return parameters;
  }

  private buildModels(): ExecutionInput['models'] | null {
    const selections: ExecutionInput['models'] = [];
    const a = {
      provider: this.modelAProvider(),
      model_id: this.modelAModel().trim(),
    };
    if (!a.provider || !a.model_id) {
      this.error.set('Choose a provider and model for Model A.');
      return null;
    }
    selections.push(a);
    if (this.mode() === 'compare') {
      const b = {
        provider: this.modelBProvider(),
        model_id: this.modelBModel().trim(),
      };
      if (!b.provider || !b.model_id) {
        this.error.set('Choose a provider and model for Model B.');
        return null;
      }
      if (a.provider === b.provider && a.model_id === b.model_id) {
        this.error.set('Pick two different models to compare.');
        return null;
      }
      selections.push(b);
    }
    return selections;
  }
}
