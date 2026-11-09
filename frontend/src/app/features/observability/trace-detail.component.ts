import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { apiErrorMessage } from '../../shared/api-error';
import { IconComponent } from '../../shared/ui/icon.component';
import {
  ObservabilityService,
  TraceDetail,
  TraceSpan,
} from './observability.service';

interface SpanNode extends TraceSpan {
  depth: number;
}

interface RequestEntry {
  key: string;
  value: string;
}

@Component({
  selector: 'msa-trace-detail',
  standalone: true,
  imports: [LocalDatePipe, RouterLink, IconComponent],
  template: `
    <div class="msa-page">
      <div class="mb-4">
        <a routerLink="/observability" class="msa-btn-ghost">
          <msa-icon name="arrow-right" [size]="13" class="rotate-180" />
          Back to observability
        </a>
      </div>

      @if (error()) {
        <p
          class="msa-card flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
          role="alert"
        >
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }

      @if (loading()) {
        <div class="msa-card p-6">
          <div class="msa-skeleton h-4 w-48"></div>
          <div class="msa-skeleton mt-4 h-24 w-full"></div>
        </div>
      } @else {
        @if (trace(); as data) {
        <header class="flex flex-wrap items-end justify-between gap-4">
          <div class="min-w-0">
            <p class="text-[11px] uppercase tracking-wide text-slate-400">
              {{ data.source_label }} · {{ data.role }} call
            </p>
            <h1 class="msa-h1 truncate">{{ data.provider_name }} · {{ data.model_id }}</h1>
            <p class="msa-sub">
              {{ data.started_at | msaDate: 'medium' }} · trace {{ data.id }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="msa-badge" [class]="statusClass(data.status)">
              {{ data.status }}
            </span>
            <span class="msa-badge bg-slate-50 capitalize text-slate-500">
              {{ data.cost_status }} cost
            </span>
          </div>
        </header>

        <div class="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Total duration</p>
            <p class="mt-1 text-xl font-semibold text-ink">
              {{ formatDuration(data.duration_ms) }}
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Provider latency</p>
            <p class="mt-1 text-xl font-semibold text-ink">
              {{ formatDuration(data.provider_latency_ms) }}
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Tokens</p>
            <p class="mt-1 text-sm font-semibold text-ink">
              {{ formatTokens(data.input_tokens, data.output_tokens) }}
            </p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">Estimated cost</p>
            <p class="mt-1 text-sm font-semibold text-ink">
              {{ data.estimated_cost ? data.estimated_cost + ' ' + data.cost_currency : 'Unavailable' }}
            </p>
            <p class="mt-1 text-[11px] text-slate-400">{{ data.cost_detail }}</p>
          </article>
          <article class="msa-card p-5">
            <p class="text-xs font-medium text-muted">OpenTelemetry</p>
            <p class="mt-1 break-all font-mono text-[11px] text-slate-600">
              {{ data.otel_trace_id || 'Not linked to an exporter' }}
            </p>
          </article>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <h2 class="msa-section-title">Request</h2>
              <span class="msa-badge bg-slate-50 text-slate-500">{{ data.request['kind'] }}</span>
            </div>
            <dl class="divide-y divide-line">
              @for (entry of requestEntries(); track entry.key) {
                <div class="px-5 py-3">
                  <dt class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    {{ entry.key }}
                  </dt>
                  <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-slate-700">
                    {{ entry.value }}
                  </dd>
                </div>
              }
            </dl>
            @if (data.link.execution_id) {
              <p class="border-t border-line px-5 py-3 text-[11px] text-slate-400">
                Playground execution {{ data.link.execution_id }}
              </p>
            } @else if (data.link.evaluation_id) {
              <p class="border-t border-line px-5 py-3 text-[11px] text-slate-400">
                Evaluation {{ data.link.evaluation_id }} · result {{ data.link.result_id }}
              </p>
            }
          </section>

          <section class="msa-card overflow-hidden">
            <div class="msa-card-header">
              <h2 class="msa-section-title">Response</h2>
              <span class="msa-badge" [class]="statusClass(data.status)">
                {{ data.status }}
              </span>
            </div>
            @if (data.error) {
              <div class="m-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
                <p class="font-medium">{{ data.error.category }}</p>
                <p class="mt-1">{{ data.error.message }}</p>
              </div>
            }
            <p class="whitespace-pre-wrap break-words px-5 py-4 text-sm text-slate-700">
              {{ data.response || (data.error ? 'No response was returned.' : 'No response content was stored.') }}
            </p>
          </section>
        </div>

        <section class="msa-card mt-4 overflow-hidden">
          <div class="msa-card-header">
            <div>
              <h2 class="msa-section-title">Spans</h2>
              <p class="text-xs text-muted">
                Operations inside this execution, ordered by start.
              </p>
            </div>
            <span class="msa-badge bg-slate-50 text-slate-500">
              {{ data.spans.length }}
            </span>
          </div>

          @if (spanNodes().length) {
            <ul class="divide-y divide-line">
              @for (span of spanNodes(); track span.id) {
                <li class="px-5 py-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <span
                      class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                      [class]="span.status === 'error' ? 'bg-rose-50 text-rose-600' : 'bg-slate-50 text-slate-500'"
                      [style.margin-left.px]="span.depth * 18"
                    >
                      <msa-icon [name]="span.status === 'error' ? 'alert' : 'activity'" [size]="13" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate font-mono text-xs font-medium text-ink">
                        {{ span.name }}
                      </span>
                      <span class="block truncate text-[11px] text-slate-400">
                        {{ span.kind }} · {{ span.status }}
                        @if (span.attributes['metric']) {
                          · metric {{ span.attributes['metric'] }}
                        }
                      </span>
                    </span>
                    <span class="text-[11px] text-slate-500">
                      {{ formatDuration(span.duration_ms) }}
                    </span>
                  </div>
                  <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100" [style.margin-left.px]="span.depth * 18">
                    <div
                      class="h-full rounded-full"
                      [class]="span.status === 'error' ? 'bg-rose-400' : 'bg-brand'"
                      [style.width.%]="spanWidth(span)"
                    ></div>
                  </div>
                  @if (spanAttributes(span)) {
                    <p class="mt-2 break-words font-mono text-[10px] text-slate-400" [style.margin-left.px]="span.depth * 18">
                      {{ spanAttributes(span) }}
                    </p>
                  }
                  @if (span.error) {
                    <p class="mt-2 rounded-lg bg-rose-50 p-2 text-[11px] text-rose-700" [style.margin-left.px]="span.depth * 18">
                      {{ span.error.category }}: {{ span.error.message }}
                    </p>
                  }
                </li>
              }
            </ul>
          } @else {
            <p class="px-5 py-8 text-center text-sm text-muted">
              This trace has no spans recorded.
            </p>
          }
        </section>
        }
      }
    </div>
  `,
})
export class TraceDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly observability = inject(ObservabilityService);

  readonly trace = signal<TraceDetail | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly spanNodes = computed<SpanNode[]>(() => {
    const spans = this.trace()?.spans ?? [];
    const byId = new Map(spans.map((span) => [span.id, span]));
    const depthOf = (span: TraceSpan): number => {
      let depth = 0;
      let current = span;
      const seen = new Set<string>();
      while (current.parent && byId.has(current.parent) && !seen.has(current.parent)) {
        seen.add(current.parent);
        depth += 1;
        current = byId.get(current.parent)!;
      }
      return depth;
    };
    return [...spans]
      .sort((left, right) => left.sequence - right.sequence)
      .map((span) => ({ ...span, depth: depthOf(span) }));
  });

  readonly requestEntries = computed<RequestEntry[]>(() => {
    const request = this.trace()?.request ?? {};
    return Object.entries(request)
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([key, value]) => ({
        key,
        value:
          typeof value === 'string'
            ? value
            : Array.isArray(value)
              ? value.length
                ? value.join('\n')
                : 'None'
              : JSON.stringify(value),
      }));
  });

  ngOnInit(): void {
    const traceId = this.route.snapshot.paramMap.get('id');
    if (!traceId) {
      this.loading.set(false);
      this.error.set('Trace not found.');
      return;
    }
    this.observability.trace(traceId).subscribe({
      next: (trace) => {
        this.trace.set(trace);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
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

  statusClass(status: string): string {
    return status === 'succeeded'
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-rose-50 text-rose-700';
  }

  spanWidth(span: TraceSpan): number {
    const total = this.trace()?.duration_ms;
    if (!total || span.duration_ms === null) {
      return 2;
    }
    return Math.max((span.duration_ms / total) * 100, 2);
  }

  spanAttributes(span: TraceSpan): string {
    return Object.entries(span.attributes)
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`)
      .join(' · ');
  }
}
