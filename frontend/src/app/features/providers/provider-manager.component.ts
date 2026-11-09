import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  OnInit,
  Output,
  SimpleChanges,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { apiErrorMessage } from '../../shared/api-error';
import { IconComponent } from '../../shared/ui/icon.component';
import {
  ProviderConfig,
  ProviderInput,
  ProviderModel,
  ProviderService,
} from './provider.service';

@Component({
  selector: 'msa-provider-manager',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent],
  template: `
    <section>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-semibold text-ink">AI providers</h3>
          <span class="msa-badge bg-slate-50 text-slate-500">
            {{ providers().length }} configured
          </span>
        </div>
        @if (canManage) {
          <button type="button" class="msa-btn-primary" (click)="toggleForm()">
            <msa-icon [name]="formOpen() ? 'close' : 'plus'" [size]="15" />
            {{ formOpen() ? 'Cancel' : 'Add provider' }}
          </button>
        }
      </div>

      @if (error()) {
        <p
          class="mt-3 flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700"
          role="alert"
        >
          <msa-icon name="alert" [size]="15" />
          <span>{{ error() }}</span>
        </p>
      }

      @if (formOpen() && canManage) {
        <form
          [formGroup]="form"
          (ngSubmit)="create()"
          class="mt-4 rounded-xl border border-line bg-canvas p-4"
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="msa-label" for="provider-name">Name</label>
              <input
                id="provider-name"
                formControlName="name"
                type="text"
                placeholder="Production Z.ai"
                class="msa-input"
              />
            </div>
            <div>
              <label class="msa-label" for="provider-kind">Kind</label>
              <select
                id="provider-kind"
                formControlName="kind"
                (change)="kindChanged()"
                class="msa-input"
              >
                <option value="ollama">Ollama (local)</option>
                <option value="zai">Z.ai (cloud)</option>
              </select>
            </div>

            @if (form.controls.kind.value === 'ollama') {
              <div class="sm:col-span-2">
                <label class="msa-label" for="provider-endpoint">
                  Endpoint
                </label>
                <input
                  id="provider-endpoint"
                  formControlName="endpoint"
                  type="text"
                  placeholder="http://host.docker.internal:11434/api"
                  class="msa-input"
                />
                <p class="mt-1 text-[11px] text-slate-400">
                  Only loopback, <code>host.docker.internal</code> and private
                  Docker hosts on port 11434 are accepted.
                </p>
              </div>
            } @else {
              <div class="sm:col-span-2">
                <label class="msa-label" for="provider-key">API key</label>
                <input
                  id="provider-key"
                  formControlName="api_key"
                  type="password"
                  autocomplete="new-password"
                  placeholder="Stored encrypted — never returned by the API"
                  class="msa-input"
                />
              </div>
            }
          </div>

          <div class="mt-4 flex justify-end gap-2">
            <button
              type="button"
              class="msa-btn-secondary"
              (click)="formOpen.set(false)"
            >
              Cancel
            </button>
            <button type="submit" [disabled]="busy()" class="msa-btn-primary">
              <msa-icon name="plus" [size]="15" /> Add provider
            </button>
          </div>
        </form>
      }

      @if (loading()) {
        <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          @for (placeholder of [1, 2, 3]; track placeholder) {
            <div class="rounded-xl border border-line bg-white p-4">
              <div class="msa-skeleton h-9 w-9"></div>
              <div class="msa-skeleton mt-3 h-3 w-28"></div>
              <div class="msa-skeleton mt-2 h-3 w-20"></div>
            </div>
          }
        </div>
      } @else if (providers().length) {
        <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          @for (provider of providers(); track provider.id) {
            <article
              class="flex flex-col rounded-xl border border-line bg-white p-4 shadow-card"
            >
              <div class="flex items-start gap-3">
                <span
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white"
                  [class]="
                    provider.kind === 'zai'
                      ? 'bg-gradient-to-br from-violet to-brand'
                      : 'bg-gradient-to-br from-amber-400 to-orange-500'
                  "
                >
                  {{ provider.kind === 'zai' ? 'Z' : 'O' }}
                </span>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium text-ink">
                    {{ provider.name }}
                  </p>
                  <p class="text-[11px] uppercase tracking-wide text-slate-400">
                    {{ provider.kind === 'zai' ? 'Cloud' : 'Local' }} ·
                    {{ provider.kind }}
                  </p>
                </div>
                <span class="msa-badge shrink-0" [class]="statusClass(provider)">
                  <span
                    class="h-1.5 w-1.5 rounded-full"
                    [class]="statusDot(provider)"
                  ></span>
                  {{ statusLabel(provider) }}
                </span>
              </div>

              @if (provider.connection_detail) {
                <p class="mt-3 line-clamp-2 text-xs text-slate-500">
                  {{ provider.connection_detail }}
                </p>
              }

              @if (modelsFor(provider.id).length) {
                <div class="mt-3 flex flex-wrap gap-1.5">
                  @for (model of modelsFor(provider.id); track model.id) {
                    <span
                      class="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-600"
                      [attr.title]="model.model_id"
                    >
                      {{ model.display_name || model.model_id }}
                    </span>
                  }
                </div>
              }

              @if (canManage) {
                <div class="mt-4 flex items-center gap-1 border-t border-line pt-3">
                  <button
                    type="button"
                    class="msa-btn-ghost"
                    [disabled]="busy()"
                    (click)="test(provider)"
                  >
                    <msa-icon name="refresh" [size]="13" /> Test
                  </button>
                  <button
                    type="button"
                    class="msa-btn-ghost"
                    [disabled]="busy()"
                    (click)="listModels(provider)"
                  >
                    <msa-icon name="database" [size]="13" /> Models
                  </button>
                  <button
                    type="button"
                    class="msa-btn-ghost ml-auto text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                    [disabled]="busy()"
                    (click)="remove(provider)"
                  >
                    <msa-icon name="trash" [size]="13" /> Remove
                  </button>
                </div>
              }
            </article>
          }
        </div>
      } @else {
        <div
          class="mt-4 flex flex-col items-center rounded-xl border border-dashed border-line bg-canvas/60 px-6 py-8 text-center"
        >
          <span
            class="flex h-11 w-11 items-center justify-center rounded-xl bg-white text-slate-400 shadow-card"
          >
            <msa-icon name="plug" [size]="20" />
          </span>
          <p class="mt-3 text-sm font-medium text-ink">
            No providers configured
          </p>
          <p class="mt-1 max-w-sm text-xs text-muted">
            Connect Z.ai for hosted models or a local Ollama runtime to evaluate
            your own deployments.
          </p>
          @if (canManage) {
            <button type="button" class="msa-btn-primary mt-4" (click)="formOpen.set(true)">
              <msa-icon name="plus" [size]="15" /> Add your first provider
            </button>
          }
        </div>
      }
    </section>
  `,
})
export class ProviderManagerComponent implements OnInit, OnChanges {
  @Input({ required: true }) projectId!: string;
  @Input() canManage = false;
  @Output() readonly changed = new EventEmitter<ProviderConfig[]>();

  private readonly service = inject(ProviderService);
  private readonly fb = inject(FormBuilder);

  readonly providers = signal<ProviderConfig[]>([]);
  readonly models = signal<Record<string, ProviderModel[]>>({});
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly formOpen = signal(false);

  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    kind: this.fb.nonNullable.control<'ollama' | 'zai'>('ollama'),
    endpoint: ['http://host.docker.internal:11434/api'],
    api_key: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['projectId'] && !changes['projectId'].firstChange) {
      this.formOpen.set(false);
      this.models.set({});
      this.load();
    }
  }

  toggleForm(): void {
    this.formOpen.update((open) => !open);
    this.error.set(null);
  }

  kindChanged(): void {
    this.form.controls.endpoint.setValue(
      this.form.controls.kind.value === 'ollama'
        ? 'http://host.docker.internal:11434/api'
        : '',
    );
  }

  modelsFor(providerId: string): ProviderModel[] {
    return this.models()[providerId] ?? [];
  }

  statusLabel(provider: ProviderConfig): string {
    if (provider.connection_status === 'connected') {
      return 'Connected';
    }
    if (provider.connection_status === 'error') {
      return 'Error';
    }
    return 'Untested';
  }

  statusClass(provider: ProviderConfig): string {
    if (provider.connection_status === 'connected') {
      return 'bg-emerald-50 text-emerald-700';
    }
    if (provider.connection_status === 'error') {
      return 'bg-rose-50 text-rose-700';
    }
    return 'bg-slate-50 text-slate-500';
  }

  statusDot(provider: ProviderConfig): string {
    if (provider.connection_status === 'connected') {
      return 'bg-emerald-500';
    }
    if (provider.connection_status === 'error') {
      return 'bg-rose-500';
    }
    return 'bg-slate-400';
  }

  create(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const input: ProviderInput = {
      name: value.name.trim(),
      kind: value.kind,
      settings: {},
      ...(value.kind === 'ollama'
        ? { endpoint: value.endpoint.trim() }
        : { api_key: value.api_key }),
    };
    this.busy.set(true);
    this.error.set(null);
    this.service.create(this.projectId, input).subscribe({
      next: (provider) => {
        const next = [...this.providers(), provider];
        this.providers.set(next);
        this.changed.emit(next);
        this.form.reset({
          name: '',
          kind: 'ollama',
          endpoint: 'http://host.docker.internal:11434/api',
          api_key: '',
        });
        this.formOpen.set(false);
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  test(provider: ProviderConfig): void {
    this.busy.set(true);
    this.error.set(null);
    this.service.test(provider.id).subscribe({
      next: (result) => {
        const next = this.providers().map((item) =>
          item.id === provider.id
            ? {
                ...item,
                connection_status:
                  result.status as ProviderConfig['connection_status'],
                connection_detail: result.detail,
              }
            : item,
        );
        this.providers.set(next);
        this.changed.emit(next);
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  listModels(provider: ProviderConfig): void {
    this.busy.set(true);
    this.error.set(null);
    this.service.models(provider.id).subscribe({
      next: (models) => {
        this.models.update((current) => ({ ...current, [provider.id]: models }));
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  remove(provider: ProviderConfig): void {
    if (!globalThis.confirm(`Remove provider ${provider.name}?`)) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.service.delete(provider.id).subscribe({
      next: () => {
        const next = this.providers().filter((item) => item.id !== provider.id);
        this.providers.set(next);
        this.changed.emit(next);
        this.models.update((current) => {
          const next = { ...current };
          delete next[provider.id];
          return next;
        });
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  private load(): void {
    if (!this.projectId) {
      return;
    }
    this.loading.set(true);
    this.service.list(this.projectId).subscribe({
      next: (providers) => {
        this.providers.set(providers);
        this.changed.emit(providers);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private fail(error: unknown): void {
    this.busy.set(false);
    this.error.set(apiErrorMessage(error));
  }
}
