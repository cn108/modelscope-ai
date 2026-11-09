import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export type SecurityTestVerdict = 'passed' | 'failed' | 'inconclusive' | '';
export type SecurityTestSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical' | '';
export type SecurityTestRunStatus = 'queued' | 'running' | 'completed' | 'failed';
export type SecurityTestResultStatus = 'pending' | 'succeeded' | 'failed';

export interface SecurityTestCaseDefinition {
  key: string;
  name: string;
  description: string;
  technique: string;
  severity: Exclude<SecurityTestSeverity, ''>;
  criteria: string;
  limitation: string;
  references: string[];
}

export interface SecurityTestCategoryDefinition {
  key: string;
  label: string;
  count: number;
  cases: SecurityTestCaseDefinition[];
}

export interface SecurityTestCatalog {
  categories: SecurityTestCategoryDefinition[];
  case_count: number;
  detectors: string[];
  disclaimer: string;
  limitations: string[];
}

export interface SecurityTestCategorySummary {
  category: string;
  label: string;
  total: number;
  passed: number;
  failed: number;
  inconclusive: number;
}

export interface SecurityTestSummary {
  total: number;
  passed: number;
  failed: number;
  inconclusive: number;
  vulnerabilities: number;
  errors: number;
  decisive: number;
  pass_rate: number | null;
  fail_rate: number | null;
  coverage: number;
  severity_counts: Record<string, number>;
  highest_severity: SecurityTestSeverity;
  categories: SecurityTestCategorySummary[];
}

export interface SecurityTestModelSummary extends SecurityTestSummary {
  id?: string;
  position?: number;
  provider?: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  parameters?: Record<string, unknown>;
  status?: 'pending' | 'running' | 'completed' | 'failed';
}

export interface SecurityTestModel {
  id: string;
  position: number;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  parameters: Record<string, unknown>;
  status: 'pending' | 'running' | 'completed' | 'failed';
  summary: SecurityTestSummary;
  error: { category: string; message: string } | null;
  created_at: string;
}

export interface SecurityTestRun {
  id: string;
  project: string;
  case_keys: string[];
  categories: string[];
  parameters: Record<string, unknown>;
  status: SecurityTestRunStatus;
  total_models: number;
  total_cases: number;
  total_results: number;
  completed_results: number;
  progress: number;
  summary: {
    totals?: SecurityTestSummary;
    severity_counts?: Record<string, number>;
    highest_severity?: SecurityTestSeverity;
    categories?: SecurityTestCategorySummary[];
    models?: SecurityTestModelSummary[];
    cases?: number;
    limitations?: string[];
  };
  error: { category: string; message: string } | null;
  created_by: string | null;
  created_by_email: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  models: SecurityTestModel[];
}

export interface SecurityTestResult {
  id: string;
  run: string;
  model: string;
  model_id: string;
  provider_name: string;
  provider_kind: string;
  position: number;
  case_key: string;
  case_name: string;
  category: string;
  category_label: string;
  technique: string;
  status: SecurityTestResultStatus;
  verdict: SecurityTestVerdict;
  severity: SecurityTestSeverity;
  rationale: string;
  evidence: string;
  matched_rules: string[];
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  error: { category: string; message: string } | null;
  executed_at: string | null;
  created_at: string;
  system_prompt?: string;
  attack_input?: string;
  response_text?: string;
  criteria?: string;
  mitigation?: string;
  references?: string[];
  provider_request_id?: string;
  updated_at?: string;
}

export interface SecurityTestDashboard {
  project: string;
  runs: number;
  completed_runs: number;
  failed_runs: number;
  running_runs: number;
  tests_performed: number;
  passed: number;
  failed: number;
  inconclusive: number;
  vulnerabilities: number;
  decisive: number;
  pass_rate: number | null;
  fail_rate: number | null;
  coverage: number;
  severity_counts: Record<string, number>;
  highest_severity: SecurityTestSeverity;
  categories: SecurityTestCategorySummary[];
  models: SecurityTestModelSummary[];
  recent_runs: SecurityTestRun[];
  recent_failures: SecurityTestResult[];
  disclaimer: string;
  limitations: string[];
}

export interface SecurityTestComparisonItem {
  case_key: string;
  model: string | null;
  baseline: SecurityTestResult | null;
  current: SecurityTestResult | null;
}

export interface SecurityTestComparison {
  project: string;
  baseline: SecurityTestRun;
  current: SecurityTestRun;
  counts: {
    baseline_total: number;
    current_total: number;
    baseline_failed: number;
    current_failed: number;
    new_failures: number;
    resolved_failures: number;
    persisting_failures: number;
    changed_verdicts: number;
  };
  baseline_summary: SecurityTestSummary;
  current_summary: SecurityTestSummary;
  models: {
    baseline: SecurityTestModelSummary[];
    current: SecurityTestModelSummary[];
  };
  warnings: string[];
  new_failures: SecurityTestComparisonItem[];
  resolved_failures: SecurityTestComparisonItem[];
  persisting: SecurityTestComparisonItem[];
  changed: SecurityTestComparisonItem[];
}

export interface SecurityTestHistoryRow {
  run: string;
  run_status: SecurityTestRunStatus;
  run_created_at: string;
  model: string;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  summary: SecurityTestSummary;
}

export interface SecurityTestModelSelection {
  provider: string;
  model_id: string;
  parameters?: Record<string, unknown>;
}

export interface SecurityTestRunInput {
  models: SecurityTestModelSelection[];
  cases: string[];
  categories?: string[];
  parameters?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class SecurityTestingService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  catalog(): Observable<SecurityTestCatalog> {
    return this.http.get<SecurityTestCatalog>(`${this.base}/security-testing/catalog/`);
  }

  dashboard(projectId: string): Observable<SecurityTestDashboard> {
    return this.http.get<SecurityTestDashboard>(
      `${this.base}/projects/${projectId}/security-testing/`,
    );
  }

  runs(projectId: string, status = ''): Observable<SecurityTestRun[]> {
    let params = new HttpParams();
    if (status) {
      params = params.set('status', status);
    }
    return this.http.get<SecurityTestRun[]>(
      `${this.base}/projects/${projectId}/security-testing/runs/`,
      { params },
    );
  }

  createRun(projectId: string, input: SecurityTestRunInput): Observable<SecurityTestRun> {
    return this.http.post<SecurityTestRun>(
      `${this.base}/projects/${projectId}/security-testing/runs/`,
      input,
    );
  }

  run(runId: string): Observable<SecurityTestRun> {
    return this.http.get<SecurityTestRun>(`${this.base}/security-test-runs/${runId}/`);
  }

  results(
    runId: string,
    filters: { model?: string; category?: string; verdict?: string; status?: string } = {},
    page = 1,
  ): Observable<Paginated<SecurityTestResult>> {
    let params = new HttpParams().set('page', page);
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    return this.http.get<Paginated<SecurityTestResult>>(
      `${this.base}/security-test-runs/${runId}/results/`,
      { params },
    );
  }

  result(resultId: string): Observable<SecurityTestResult> {
    return this.http.get<SecurityTestResult>(
      `${this.base}/security-test-results/${resultId}/`,
    );
  }

  rerun(runId: string): Observable<SecurityTestRun> {
    return this.http.post<SecurityTestRun>(
      `${this.base}/security-test-runs/${runId}/rerun/`,
      {},
    );
  }

  compare(
    projectId: string,
    baseline: string,
    current: string,
  ): Observable<SecurityTestComparison> {
    return this.http.get<SecurityTestComparison>(
      `${this.base}/projects/${projectId}/security-testing/compare/`,
      { params: new HttpParams().set('baseline', baseline).set('current', current) },
    );
  }

  history(
    projectId: string,
    filters: { model?: string; provider?: string } = {},
  ): Observable<SecurityTestHistoryRow[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    return this.http.get<SecurityTestHistoryRow[]>(
      `${this.base}/projects/${projectId}/security-testing/history/`,
      { params },
    );
  }
}
