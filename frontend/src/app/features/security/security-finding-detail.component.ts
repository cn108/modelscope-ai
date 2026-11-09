import { DatePipe } from '@angular/common';
import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  inject,
  signal,
} from '@angular/core';

import { apiErrorMessage } from '../../shared/api-error';
import { IconComponent } from '../../shared/ui/icon.component';
import {
  FindingUpdate,
  SecurityFinding,
  SecurityService,
} from './security.service';

@Component({
  selector: 'msa-security-finding-detail',
  standalone: true,
  imports: [DatePipe, IconComponent],
  template: `
    <div
      class="fixed inset-0 z-50 flex items-start justify-end bg-navy/40 p-0 backdrop-blur-sm sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Security finding detail"
      (click)="closed.emit()"
    >
      <section
        class="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl sm:rounded-2xl"
        (click)="$event.stopPropagation()"
      >
        <header class="sticky top-0 z-10 flex items-start gap-3 border-b border-line bg-white/95 px-5 py-4 backdrop-blur">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600">
            <msa-icon name="shield" [size]="19" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              Security finding · {{ finding.category }}
            </p>
            <h2 class="mt-1 text-lg font-semibold leading-tight text-ink">
              {{ finding.title }}
            </h2>
            <div class="mt-2 flex flex-wrap items-center gap-1.5">
              <span class="msa-badge" [class]="severityClass(finding.severity)">
                {{ finding.severity }}
              </span>
              <span class="msa-badge" [class]="dispositionClass(finding.disposition)">
                {{ finding.disposition }}
              </span>
              <span class="msa-badge" [class]="classificationClass(finding.classification)">
                {{ finding.classification === 'confirmed_vulnerability' ? 'Confirmed vulnerability' : 'Potential risk' }}
              </span>
              <span class="msa-badge" [class]="statusClass(finding.status)">
                {{ finding.status }}
              </span>
            </div>
          </div>
          <button type="button" class="msa-icon-btn" title="Close finding" (click)="closed.emit()">
            <msa-icon name="close" [size]="16" />
          </button>
        </header>

        <div class="space-y-5 px-5 py-5">
          @if (error()) {
            <p class="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
              <msa-icon name="alert" [size]="15" />
              <span>{{ error() }}</span>
            </p>
          }

          <p class="text-sm leading-relaxed text-slate-600">{{ finding.description }}</p>

          <div class="grid gap-3 sm:grid-cols-2">
            <div class="rounded-xl border border-line bg-canvas/50 p-3">
              <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Affected resource</p>
              <p class="mt-1 text-sm font-medium text-ink">{{ finding.resource.label }}</p>
              <p class="mt-0.5 text-[11px] text-slate-500">
                {{ finding.resource.type }} · {{ finding.resource.location || 'whole resource' }}
              </p>
            </div>
            <div class="rounded-xl border border-line bg-canvas/50 p-3">
              <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Detection reference</p>
              <p class="mt-1 text-sm font-medium text-ink">
                {{ finding.scan_target.label }}
              </p>
              <p class="mt-0.5 text-[11px] text-slate-500">
                Scan {{ shortId(finding.scan) }} · detected {{ finding.detected_at | date: 'medium' }}
              </p>
            </div>
          </div>

          <section>
            <h3 class="text-sm font-semibold text-ink">Why this was flagged</h3>
            <p class="mt-1 text-xs text-muted">
              Evidence is redacted. The detector matched a pattern; that is a signal for review,
              not proof that an exploit or data breach occurred.
            </p>
            <pre class="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-navy p-3 font-mono text-[11px] leading-relaxed text-slate-200">{{ finding.evidence }}</pre>
            <p class="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-400">
              <span>Rule: {{ finding.rule_id || finding.check }}</span>
              @if (finding.metadata['occurrences']) {
                <span>· {{ finding.metadata['occurrences'] }} occurrence(s)</span>
              }
            </p>
          </section>

          <section class="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4">
            <h3 class="flex items-center gap-2 text-sm font-semibold text-emerald-900">
              <msa-icon name="check-circle" [size]="15" /> Recommended remediation
            </h3>
            <p class="mt-1.5 text-sm leading-relaxed text-emerald-900/80">{{ finding.remediation }}</p>
          </section>

          <section>
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-sm font-semibold text-ink">Review history</h3>
              <span class="text-[11px] text-slate-400">
                {{ finding.status_history.length }} event{{ finding.status_history.length === 1 ? '' : 's' }}
              </span>
            </div>
            <ol class="mt-2 space-y-2 border-l border-line pl-4">
              @for (event of finding.status_history; track event.id) {
                <li class="relative">
                  <span class="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand"></span>
                  <p class="text-xs font-medium text-ink">
                    {{ event.from_status || 'detected' }} → {{ event.to_status }}
                  </p>
                  <p class="text-[11px] text-slate-500">
                    {{ event.actor_email || 'System' }} · {{ event.created_at | date: 'medium' }}
                  </p>
                  @if (event.note) {
                    <p class="mt-0.5 text-[11px] text-slate-600">{{ event.note }}</p>
                  }
                </li>
              }
            </ol>
          </section>

          <section class="rounded-xl border border-line p-4">
            <h3 class="text-sm font-semibold text-ink">Review this finding</h3>
            <p class="mt-1 text-[11px] text-muted">
              Reviewing or resolving does not delete the original detection. The history above is retained.
            </p>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Review status</span>
                <select class="msa-input" [value]="status()" (change)="status.set($any($event.target).value)">
                  <option value="open">Open</option>
                  <option value="reviewed">Reviewed</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
              <label class="text-xs text-muted">
                <span class="msa-label mb-1">Classification</span>
                <select class="msa-input" [value]="classification()" (change)="classification.set($any($event.target).value)">
                  <option value="risk">Potential risk</option>
                  <option value="confirmed_vulnerability">Confirmed vulnerability</option>
                </select>
              </label>
            </div>
            <label class="mt-3 block text-xs text-muted">
              <span class="msa-label mb-1">Review note</span>
              <textarea
                class="msa-input min-h-[72px]"
                [value]="note()"
                (input)="note.set($any($event.target).value)"
                placeholder="Record what you verified and the action taken."
              ></textarea>
            </label>
            <div class="mt-3 flex items-center justify-between gap-2">
              <p class="text-[10px] text-slate-400">
                You can confirm a real vulnerability or leave this as a potential risk.
              </p>
              <button type="button" class="msa-btn-primary" [disabled]="saving()" (click)="save()">
                @if (saving()) {
                  <msa-icon name="refresh" [size]="14" class="animate-spin" /> Saving
                } @else {
                  <msa-icon name="check" [size]="14" /> Save review
                }
              </button>
            </div>
          </section>

          <p class="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
            <msa-icon name="alert" [size]="14" class="mt-0.5 shrink-0" />
            <span>
              This detector is heuristic. Findings can be false positives, and a clean scan does not
              prove that the resource is safe. Review the evidence in context.
            </span>
          </p>
        </div>
      </section>
    </div>
  `,
})
export class SecurityFindingDetailComponent implements OnChanges {
  private readonly security = inject(SecurityService);

  @Input({ required: true }) finding!: SecurityFinding;
  @Output() closed = new EventEmitter<void>();
  @Output() updated = new EventEmitter<SecurityFinding>();

  readonly status = signal<'open' | 'reviewed' | 'resolved'>('open');
  readonly classification = signal<'risk' | 'confirmed_vulnerability'>('risk');
  readonly note = signal('');
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['finding']) {
      this.status.set(this.finding.status);
      this.classification.set(this.finding.classification);
      this.note.set('');
      this.error.set(null);
    }
  }

  save(): void {
    const input: FindingUpdate = {
      status: this.status(),
      classification: this.classification(),
      note: this.note().trim(),
    };
    this.saving.set(true);
    this.error.set(null);
    this.security.updateFinding(this.finding.id, input).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.updated.emit(updated);
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
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

  classificationClass(classification: string): string {
    return classification === 'confirmed_vulnerability'
      ? 'bg-rose-50 text-rose-700'
      : 'bg-slate-50 text-slate-500';
  }

  statusClass(status: string): string {
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
}
