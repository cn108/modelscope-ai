import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export interface MetricDefinition {
  key: string;
  label: string;
  description: string;
  requires_expected_output: boolean;
  requires_context: boolean;
  requires_judge: boolean;
  threshold: number | null;
  source: 'builtin' | 'deepeval';
}

export interface MetricResult {
  metric: string;
  label: string;
  score: number | null;
  passed: boolean | null;
  threshold: number | null;
  metric_version?: string;
  reason: string;
  error: string | null;
}

export interface EvaluationError {
  category: string;
  message: string;
}

export interface EvaluationModelSummary {
  id: string;
  position: number;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  cases: number;
  succeeded: number;
  failed: number;
  avg_latency_ms: number | null;
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  metric_averages: Record<string, number>;
  metric_scored_counts: Record<string, number>;
}

export interface EvaluationModel {
  id: string;
  position: number;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  parameters: Record<string, unknown>;
  status: 'pending' | 'running' | 'completed' | 'failed';
  summary: Partial<EvaluationModelSummary>;
  error: EvaluationError | null;
}

export interface Evaluation {
  id: string;
  project: string;
  dataset: string | null;
  dataset_name: string;
  dataset_version: number;
  status: 'queued' | 'running' | 'completed' | 'failed';
  metrics: string[];
  parameters: Record<string, unknown>;
  judge: { provider: string | null; provider_name: string; model_id: string } | null;
  total_cases: number;
  total_results: number;
  completed_cases: number;
  failed_cases: number;
  summary: {
    metrics?: string[];
    models?: EvaluationModelSummary[];
    totals?: {
      models: number;
      records: number;
      case_results: number;
      succeeded: number;
      failed: number;
    };
    judge?: { provider_name: string; model_id: string } | null;
    judge_calls?: number;
  };
  review_summary: EvaluationReviewSummary;
  error: EvaluationError | null;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  models: EvaluationModel[];
}

export interface EvaluationReview {
  id: string;
  reviewer: string | null;
  reviewer_email: string;
  label: 'pass' | 'fail' | 'unsure';
  note: string;
  created_at: string;
  updated_at: string;
}

export interface EvaluationReviewSummary {
  total_reviews: number;
  reviewed_results: number;
  labels: Record<string, number>;
  disagreements: number;
  agreement_rate: number | null;
}

export interface EvaluationResultRow {
  id: string;
  model: string;
  model_id: string;
  provider_name: string;
  position: number;
  record_position: number;
  input: string;
  expected_output: string;
  context: string[];
  generated_response: string;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  status: 'pending' | 'succeeded' | 'failed';
  scores: Record<string, number>;
  metric_results: MetricResult[];
  reviews: EvaluationReview[];
  error: EvaluationError | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationModelInput {
  provider: string;
  model_id: string;
  parameters?: Record<string, unknown>;
}

export interface EvaluationInput {
  dataset: string;
  metrics: string[];
  models: EvaluationModelInput[];
  parameters?: Record<string, unknown>;
  judge?: { provider: string; model_id: string } | null;
}

@Injectable({ providedIn: 'root' })
export class EvaluationService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  metrics(): Observable<{ metrics: MetricDefinition[] }> {
    return this.http.get<{ metrics: MetricDefinition[] }>(
      `${this.base}/evaluation-metrics/`,
    );
  }

  list(projectId: string): Observable<Evaluation[]> {
    return this.http.get<Evaluation[]>(
      `${this.base}/projects/${projectId}/evaluations/`,
    );
  }

  create(projectId: string, input: EvaluationInput): Observable<Evaluation> {
    return this.http.post<Evaluation>(
      `${this.base}/projects/${projectId}/evaluations/`,
      input,
    );
  }

  get(evaluationId: string): Observable<Evaluation> {
    return this.http.get<Evaluation>(`${this.base}/evaluations/${evaluationId}/`);
  }

  results(
    evaluationId: string,
    options: { model?: string; status?: string; page?: number } = {},
  ): Observable<Paginated<EvaluationResultRow>> {
    let params = new HttpParams();
    if (options.model) {
      params = params.set('model', options.model);
    }
    if (options.status) {
      params = params.set('status', options.status);
    }
    params = params.set('page', options.page ?? 1);
    return this.http.get<Paginated<EvaluationResultRow>>(
      `${this.base}/evaluations/${evaluationId}/results/`,
      { params },
    );
  }

  rerun(evaluationId: string): Observable<Evaluation> {
    return this.http.post<Evaluation>(
      `${this.base}/evaluations/${evaluationId}/rerun/`,
      {},
    );
  }

  saveReview(
    evaluationId: string,
    resultId: string,
    label: EvaluationReview['label'],
    note: string,
  ): Observable<EvaluationReview> {
    return this.http.post<EvaluationReview>(
      `${this.base}/evaluations/${evaluationId}/results/${resultId}/reviews/`,
      { label, note },
    );
  }
}
