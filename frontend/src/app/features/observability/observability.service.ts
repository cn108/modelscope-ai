import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export interface ObservabilityTotals {
  calls: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  avg_duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  token_calls: number;
  estimated_cost_calls: number;
  unavailable_cost_calls: number;
  first_seen: string | null;
  last_seen: string | null;
  roles: Record<string, number>;
}

export interface CostAmount {
  currency: string;
  amount: string;
  calls: number;
}

export interface UsageRow {
  provider_id: string | null;
  provider_name: string;
  provider_kind: string;
  model_id?: string;
  count: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  avg_duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  token_calls: number;
  costs: CostAmount[];
  estimated_calls: number;
  cost_status: 'estimated' | 'partial' | 'unavailable';
  failure_rate: number;
  roles: Record<string, number>;
  last_seen: string | null;
}

export interface TrendPoint {
  day: string;
  count: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  costs: CostAmount[];
}

export interface TraceError {
  category: string;
  message: string;
}

export interface TraceSummary {
  id: string;
  project: string;
  source: 'playground' | 'evaluation';
  source_label: string;
  role: 'model' | 'judge';
  status: 'succeeded' | 'failed';
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  started_at: string;
  ended_at: string;
  duration_ms: number | null;
  provider_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost: string | null;
  cost_currency: string;
  cost_status: 'estimated' | 'unavailable';
  cost_detail: string;
  error: TraceError | null;
  otel_trace_id: string;
  request_preview: string;
  link: {
    source: string;
    execution_id?: string;
    evaluation_id?: string;
    result_id?: string;
  };
}

export interface TraceSpan {
  id: string;
  parent: string | null;
  sequence: number;
  name: string;
  kind: 'internal' | 'client' | 'task';
  status: 'ok' | 'error' | 'unset';
  started_at: string;
  ended_at: string;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  error: TraceError | null;
}

export interface TraceDetail extends TraceSummary {
  request: Record<string, unknown>;
  response: string;
  attributes: Record<string, unknown>;
  spans: TraceSpan[];
}

export interface ObservabilityDashboard {
  project: string;
  totals: ObservabilityTotals;
  costs: CostAmount[];
  cost_status: 'estimated' | 'partial' | 'unavailable';
  cost_detail: string;
  models: UsageRow[];
  providers: UsageRow[];
  trend: TrendPoint[];
  errors: { category: string; count: number }[];
  slowest: TraceSummary[];
  rollups?: {
    enabled: boolean;
    through: string | null;
    from: string | null;
    to: string | null;
    retention_days: number;
  };
  facets: {
    providers: { id: string | null; name: string; kind: string }[];
    models: string[];
  };
  telemetry: {
    enabled: boolean;
    exported: boolean;
    detail: string;
    provider_configured?: boolean;
    service_name?: string;
  };
}

export interface ObservabilityFilters {
  from?: string;
  to?: string;
  provider?: string;
  model?: string;
  status?: string;
  source?: string;
  role?: string;
}

@Injectable({ providedIn: 'root' })
export class ObservabilityService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  dashboard(
    projectId: string,
    filters: ObservabilityFilters = {},
  ): Observable<ObservabilityDashboard> {
    return this.http.get<ObservabilityDashboard>(
      `${this.base}/projects/${projectId}/observability/`,
      { params: this.params(filters) },
    );
  }

  traces(
    projectId: string,
    filters: ObservabilityFilters = {},
    page = 1,
  ): Observable<Paginated<TraceSummary>> {
    return this.http.get<Paginated<TraceSummary>>(
      `${this.base}/projects/${projectId}/observability/traces/`,
      { params: this.params(filters).set('page', page) },
    );
  }

  trace(traceId: string): Observable<TraceDetail> {
    return this.http.get<TraceDetail>(`${this.base}/observability/traces/${traceId}/`);
  }

  private params(filters: ObservabilityFilters): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, value);
      }
    }
    return params;
  }
}
