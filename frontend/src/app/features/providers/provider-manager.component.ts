import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { apiErrorMessage } from '../../shared/api-error';
import { ProviderConfig, ProviderInput, ProviderModel, ProviderService } from './provider.service';

@Component({
  selector: 'msa-provider-manager',
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <section class="mt-3 border-t border-slate-100 pt-3">
      @if (error()) { <p class="mb-2 text-xs text-red-700">{{ error() }}</p> }
      @if (canManage) {
        <form [formGroup]="form" (ngSubmit)="create()" class="grid gap-2 sm:grid-cols-2">
          <input formControlName="name" placeholder="Provider name" class="rounded border border-slate-300 px-2 py-1.5 text-xs" />
          <select formControlName="kind" (change)="kindChanged()" class="rounded border border-slate-300 px-2 py-1.5 text-xs">
            <option value="ollama">Ollama (local)</option><option value="zai">Z.ai (cloud)</option>
          </select>
          @if (form.controls.kind.value === 'ollama') {
            <input formControlName="endpoint" placeholder="http://host.docker.internal:11434/api" class="rounded border border-slate-300 px-2 py-1.5 text-xs sm:col-span-2" />
          } @else {
            <input formControlName="api_key" type="password" autocomplete="new-password" placeholder="Z.ai API key — encrypted at rest" class="rounded border border-slate-300 px-2 py-1.5 text-xs sm:col-span-2" />
          }
          <button type="submit" [disabled]="busy()" class="rounded bg-slate-800 px-2 py-1.5 text-xs text-white disabled:opacity-60 sm:col-span-2">Add provider</button>
        </form>
      }
      @if (loading()) { <p class="mt-2 text-xs text-slate-400">Loading providers…</p> }
      @for (provider of providers(); track provider.id) {
        <article class="mt-2 rounded border border-slate-100 p-2 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span class="font-medium">{{ provider.name }} · {{ provider.kind }} · {{ provider.connection_status }}</span>
            @if (canManage) {
              <div class="flex gap-2">
                <button type="button" (click)="test(provider)" [disabled]="busy()" class="underline">Test</button>
                <button type="button" (click)="listModels(provider)" [disabled]="busy()" class="underline">Models</button>
                <button type="button" (click)="remove(provider)" [disabled]="busy()" class="text-red-600 underline">Remove</button>
              </div>
            }
          </div>
          @if (provider.connection_detail) { <p class="mt-1 text-slate-500">{{ provider.connection_detail }}</p> }
          @for (model of models()[provider.id]; track model.id) {
            <p class="mt-1 text-slate-600">{{ model.display_name || model.model_id }} <span class="text-slate-400">({{ model.model_id }})</span></p>
          }
        </article>
      } @empty {
        @if (!loading()) { <p class="mt-2 text-xs text-slate-400">No providers configured for this project.</p> }
      }
    </section>
  `,
})
export class ProviderManagerComponent implements OnInit {
  @Input({ required: true }) projectId!: string;
  @Input() canManage = false;

  private readonly service = inject(ProviderService);
  private readonly fb = inject(FormBuilder);
  readonly providers = signal<ProviderConfig[]>([]);
  readonly models = signal<Record<string, ProviderModel[]>>({});
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    kind: this.fb.nonNullable.control<'ollama' | 'zai'>('ollama'),
    endpoint: ['http://host.docker.internal:11434/api'],
    api_key: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  kindChanged(): void {
    this.form.controls.endpoint.setValue(
      this.form.controls.kind.value === 'ollama' ? 'http://host.docker.internal:11434/api' : '',
    );
  }

  create(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue();
    const input: ProviderInput = {
      name: value.name.trim(),
      kind: value.kind,
      settings: {},
      ...(value.kind === 'ollama' ? { endpoint: value.endpoint.trim() } : { api_key: value.api_key }),
    };
    this.busy.set(true);
    this.error.set(null);
    this.service.create(this.projectId, input).subscribe({
      next: (provider) => {
        this.providers.update((items) => [...items, provider]);
        this.form.reset({ name: '', kind: 'ollama', endpoint: 'http://host.docker.internal:11434/api', api_key: '' });
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  test(provider: ProviderConfig): void {
    this.busy.set(true);
    this.service.test(provider.id).subscribe({
      next: (result) => {
        this.providers.update((items) => items.map((item) => item.id === provider.id
          ? { ...item, connection_status: result.status as ProviderConfig['connection_status'], connection_detail: result.detail }
          : item));
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  listModels(provider: ProviderConfig): void {
    this.busy.set(true);
    this.service.models(provider.id).subscribe({
      next: (models) => { this.models.update((current) => ({ ...current, [provider.id]: models })); this.busy.set(false); },
      error: (error: unknown) => this.fail(error),
    });
  }

  remove(provider: ProviderConfig): void {
    if (!globalThis.confirm(`Remove provider ${provider.name}?`)) return;
    this.busy.set(true);
    this.service.delete(provider.id).subscribe({
      next: () => {
        this.providers.update((items) => items.filter((item) => item.id !== provider.id));
        this.models.update((current) => { const next = { ...current }; delete next[provider.id]; return next; });
        this.busy.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  private load(): void {
    this.service.list(this.projectId).subscribe({
      next: (providers) => { this.providers.set(providers); this.loading.set(false); },
      error: (error: unknown) => { this.loading.set(false); this.error.set(apiErrorMessage(error)); },
    });
  }

  private fail(error: unknown): void {
    this.busy.set(false);
    this.error.set(apiErrorMessage(error));
  }
}
