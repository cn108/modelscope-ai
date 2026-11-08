import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { ApiService } from '../../core/authentication/api.service';
import { HealthResponse } from '../../shared/models/health.model';

@Component({
  selector: 'msa-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <main class="mx-auto max-w-3xl p-8">
      <h1 class="text-2xl font-semibold tracking-tight">ModelScope AI</h1>
      <p class="mt-1 text-sm text-slate-500">Foundation status (Milestone 1)</p>

      @if (health(); as h) {
        <div class="mt-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div class="flex items-center gap-2">
            <span
              class="inline-block h-2.5 w-2.5 rounded-full"
              [class]="h.status === 'ok' ? 'bg-emerald-500' : 'bg-red-500'"
            ></span>
            <span class="font-medium">{{ h.service }} — {{ h.status }}</span>
          </div>
          <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
            <dt class="text-slate-500">Database</dt>
            <dd>{{ h.database.status }} ({{ h.database.engine ?? 'unknown' }})</dd>
          </dl>
        </div>
      } @else if (error()) {
        <div class="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          API unreachable: {{ error() }}
        </div>
      } @else {
        <p class="mt-6 text-sm text-slate-400">Checking API…</p>
      }
    </main>
  `,
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly health = signal<HealthResponse | null>(null);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.api.getHealth().subscribe({
      next: (h) => this.health.set(h),
      error: (err) => this.error.set(err.message ?? 'unknown error'),
    });
  }
}
