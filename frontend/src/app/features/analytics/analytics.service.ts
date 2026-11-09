import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface AnalyticsCost {
  currency: string;
  amount: string;
  calls: number;
}

export interface AnalyticsRange {
  from: string;
  to: string;
  days: number;
  defaulted: boolean;
  timezone: string;
}

export interface AnalyticsFilterState {
  from: string;
  to: string;
  provider: string | null;
  provider_name: string;
  model: string | null;
  source: string | null;
}

export interface AnalyticsModelUsage {
  provider_id: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  count: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  token_calls: number;
  costs: AnalyticsCost[];
  estimated_calls: number;
  unavailable_calls: number;
  cost_status: 'estimated' | 'partial' | 'unavailable';
  failure_rate: number;
  evaluation?: {
    runs: number;
    avg_score: number | null;
    scored_metrics: number;
  };
}

export interface AnalyticsProviderUsage {
  provider_id: string | null;
  provider_name: string;
  provider_kind: string;
  count: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  costs: AnalyticsCost[];
  cost_status: 'estimated' | 'partial' | 'unavailable';
}

export interface AnalyticsTrendPoint {
  day: string;
  calls: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  costs: AnalyticsCost[];
  executions: number;
  executions_succeeded: number;
  executions_partial: number;
  executions_failed: number;
  evaluations: number;
  avg_evaluation_score: number | null;
  security_scans: number;
  security_findings: number;
}

export interface EvaluationHistoryModel {
  id: string;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  status: string;
  cases: number;
  failed: number;
  avg_score: number | null;
  scored_metrics: number;
}

export interface EvaluationHistory {
  id: string;
  dataset_name: string;
  dataset_version: number;
  status: string;
  metrics: string[];
  total_cases: number;
  failed_cases: number;
  created_at: string;
  avg_score: number | null;
  scored_metrics: number;
  models: EvaluationHistoryModel[];
}

export interface SecurityRecentScan {
  id: string;
  target_type: string;
  target_label: string;
  status: string;
  finding_count: number;
  highest_severity: string;
  created_at: string;
  completed_at: string | null;
}

export interface AnalyticsDashboard {
  project: string;
  workspace: string;
  generated_at: string;
  range: AnalyticsRange;
  filters: AnalyticsFilterState;
  summary: {
    executions: {
      total: number;
      succeeded: number;
      partial: number;
      failed: number;
      success_rate: number;
    };
    model_calls: {
      total: number;
      succeeded: number;
      failed: number;
      failure_rate: number;
      avg_latency_ms: number | null;
      avg_duration_ms: number | null;
      input_tokens: number | null;
      output_tokens: number | null;
      token_calls: number;
      calls_without_tokens: number;
      cost_status: 'estimated' | 'partial' | 'unavailable';
      cost_detail: string;
      costs: AnalyticsCost[];
      estimated_calls: number;
      unavailable_calls: number;
    };
    evaluations: {
      total: number;
      completed: number;
      failed: number;
      running: number;
      avg_score: number | null;
      scored_models: number;
      scored_metrics: number;
    };
    security: {
      scans: number;
      completed_scans: number;
      failed_scans: number;
      running_scans: number;
      findings: number;
      open_findings: number;
      reviewed_findings: number;
      resolved_findings: number;
      severity_counts: Record<string, number>;
      categories: { category: string; count: number }[];
      recent_scans: SecurityRecentScan[];
      note: string;
    };
  };
  cost: {
    status: 'estimated' | 'partial' | 'unavailable';
    detail: string;
    currencies: AnalyticsCost[];
    estimated_calls: number;
    unavailable_calls: number;
    by_model: {
      model_id: string;
      provider_name: string;
      costs: AnalyticsCost[];
      estimated_calls: number;
      cost_status: string;
    }[];
    by_provider: {
      provider_name: string;
      provider_kind: string;
      costs: AnalyticsCost[];
      estimated_calls: number;
      cost_status: string;
    }[];
    note: string;
  };
  usage: {
    models: AnalyticsModelUsage[];
    providers: AnalyticsProviderUsage[];
  };
  evaluation_history: EvaluationHistory[];
  trend: AnalyticsTrendPoint[];
  errors: { category: string; count: number }[];
  facets: {
    providers: { id: string | null; name: string; kind: string }[];
    models: string[];
  };
  data_quality: {
    model_calls_without_tokens: number;
    calls_without_cost_estimate: number;
    evaluations_without_scores: number;
    failed_security_scans: number;
  };
  limitations: string[];
  scope_notes: string[];
  rollups: {
    enabled?: boolean;
    through?: string | null;
    from?: string | null;
    to?: string | null;
    retention_days?: number;
  };
  telemetry: Record<string, unknown>;
}

export interface ModelTrendPoint {
  day: string;
  calls: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  costs: AnalyticsCost[];
  avg_evaluation_score: number | null;
}

export interface ModelPerformance {
  key: string;
  provider_id: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  calls: number;
  succeeded: number;
  failed: number;
  failure_rate: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  token_calls: number;
  costs: AnalyticsCost[];
  estimated_calls: number;
  unavailable_calls: number;
  cost_status: 'estimated' | 'partial' | 'unavailable';
  evaluation: {
    runs: number;
    avg_score: number | null;
    scored_metrics: number;
  };
  trend: ModelTrendPoint[];
}

export interface ModelPerformanceResponse {
  project: string;
  workspace: string;
  generated_at: string;
  range: AnalyticsRange;
  filters: AnalyticsFilterState;
  models: ModelPerformance[];
  comparison_note: string;
  warnings: string[];
}

export type ReportSectionKey =
  | 'overview'
  | 'usage'
  | 'performance'
  | 'evaluations'
  | 'costs'
  | 'security'
  | 'trends';

export interface ReportSectionDefinition {
  key: ReportSectionKey;
  label: string;
}

export const REPORT_SECTIONS: ReportSectionDefinition[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'usage', label: 'Model usage' },
  { key: 'performance', label: 'Model performance' },
  { key: 'evaluations', label: 'Evaluation outcomes' },
  { key: 'costs', label: 'Costs' },
  { key: 'security', label: 'Security' },
  { key: 'trends', label: 'Daily trends' },
];

export interface AnalyticsReportSummary {
  id: string;
  project: string;
  title: string;
  sections: ReportSectionKey[];
  section_labels: string[];
  period_from: string;
  period_to: string;
  filters: Record<string, unknown>;
  scope: Record<string, unknown>;
  schema_version: number;
  created_by: string | null;
  created_by_email: string;
  created_at: string;
}

export interface ReportDocument {
  title: string;
  metadata: [string, string][];
  sections: {
    key: ReportSectionKey;
    title: string;
    rows: [string, string][];
  }[];
  notes: string[];
}

export interface AnalyticsReportDetail extends AnalyticsReportSummary {
  document: ReportDocument;
}

export interface AnalyticsReportInput {
  title: string;
  from?: string;
  to?: string;
  provider?: string;
  model?: string;
  source?: string;
  sections: ReportSectionKey[];
}

export interface AnalyticsFilters {
  from?: string;
  to?: string;
  provider?: string;
  model?: string;
  source?: string;
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  dashboard(projectId: string, filters: AnalyticsFilters = {}): Observable<AnalyticsDashboard> {
    return this.http.get<AnalyticsDashboard>(
      `${this.base}/projects/${projectId}/analytics/`,
      { params: this.params(filters) },
    );
  }

  models(
    projectId: string,
    filters: AnalyticsFilters = {},
  ): Observable<ModelPerformanceResponse> {
    return this.http.get<ModelPerformanceResponse>(
      `${this.base}/projects/${projectId}/analytics/models/`,
      { params: this.params(filters) },
    );
  }

  reports(projectId: string): Observable<AnalyticsReportSummary[]> {
    return this.http.get<AnalyticsReportSummary[]>(
      `${this.base}/projects/${projectId}/analytics/reports/`,
    );
  }

  report(reportId: string): Observable<AnalyticsReportDetail> {
    return this.http.get<AnalyticsReportDetail>(
      `${this.base}/analytics-reports/${reportId}/`,
    );
  }

  createReport(
    projectId: string,
    input: AnalyticsReportInput,
  ): Observable<AnalyticsReportDetail> {
    return this.http.post<AnalyticsReportDetail>(
      `${this.base}/projects/${projectId}/analytics/reports/`,
      input,
    );
  }

  exportReport(reportId: string, format: 'csv' | 'pdf'): Observable<Blob> {
    return this.http.get(
      `${this.base}/analytics-reports/${reportId}/export/`,
      {
        params: new HttpParams().set('export_format', format),
        responseType: 'blob',
      },
    );
  }

  private params(filters: AnalyticsFilters): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, value);
      }
    }
    return params;
  }
}
