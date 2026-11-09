import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export type SecuritySeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type SecurityTargetType = 'dataset' | 'prompt' | 'execution';

export interface SecurityCheckDefinition {
  key: string;
  label: string;
  description: string;
  applies_to: string[];
  limitation: string;
}

export interface SecurityPiiCategory {
  key: string;
  label: string;
  severity: SecuritySeverity;
  description: string;
}

export interface SecurityCheckCatalog {
  checks: SecurityCheckDefinition[];
  pii_categories: SecurityPiiCategory[];
  disclaimer: string;
}

export interface SecurityScanTarget {
  type: SecurityTargetType;
  label: string;
  identifier: string;
  version: string;
  dataset: string | null;
  prompt: string | null;
  execution: string | null;
}

export interface SecurityScanSummary {
  checks: string[];
  target: {
    type: SecurityTargetType;
    label: string;
    version: string;
    identifier: string;
  };
  severity_counts: Record<string, number>;
  category_counts: { category: string; count: number }[];
  status_counts: Record<string, number>;
  disposition_counts: Record<string, number>;
  highest_severity: SecuritySeverity | '';
  truncated: boolean;
  limitations: string[];
}

export interface SecurityScan {
  id: string;
  project: string;
  target_type: SecurityTargetType;
  target: SecurityScanTarget;
  target_label: string;
  target_identifier: string;
  target_version: string;
  checks: string[];
  config: Record<string, unknown>;
  blocking_enabled: boolean;
  blocking_severity: SecuritySeverity;
  blocking_reason: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  total_items: number;
  scanned_items: number;
  finding_count: number;
  highest_severity: SecuritySeverity | '';
  summary: SecurityScanSummary;
  error: { category: string; message: string } | null;
  created_by: string | null;
  created_by_email: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface SecurityFindingEvent {
  id: string;
  from_status: string;
  to_status: 'open' | 'reviewed' | 'resolved';
  note: string;
  actor: string | null;
  actor_email: string;
  created_at: string;
}

export interface SecurityFinding {
  id: string;
  scan: string;
  project: string;
  check: string;
  category: string;
  title: string;
  description: string;
  severity: SecuritySeverity;
  disposition: 'informational' | 'warning' | 'blocking';
  classification: 'risk' | 'confirmed_vulnerability';
  resource: {
    type: string;
    id: string;
    label: string;
    location: string;
  };
  resource_type: string;
  resource_id: string;
  resource_label: string;
  location: string;
  evidence: string;
  remediation: string;
  rule_id: string;
  detected_at: string;
  execution: string | null;
  execution_result: string | null;
  metadata: Record<string, unknown>;
  status: 'open' | 'reviewed' | 'resolved';
  reviewed_by: string | null;
  reviewed_by_email: string;
  reviewed_at: string | null;
  resolved_at: string | null;
  resolution_note: string;
  status_history: SecurityFindingEvent[];
  scan_target: {
    id: string;
    type: SecurityTargetType;
    label: string;
    version: string;
  };
  updated_at: string;
}

export interface SecurityFindingChange {
  baseline: SecurityFinding;
  current: SecurityFinding;
  changed_fields: string[];
}

export interface SecurityScanComparison {
  project: string;
  baseline: SecurityScan;
  current: SecurityScan;
  counts: {
    baseline_total: number;
    current_total: number;
    new: number;
    resolved: number;
    persisting: number;
    changed: number;
  };
  target: {
    type: SecurityTargetType;
    identifier: string;
    label: string;
    baseline_version: string;
    current_version: string;
    version_changed: boolean;
  };
  checks: {
    baseline: string[];
    current: string[];
    match: boolean;
  };
  warnings: string[];
  new_findings: SecurityFinding[];
  resolved_findings: SecurityFinding[];
  persisting: SecurityFindingChange[];
}

export interface SecurityDashboard {
  project: string;
  scans: number;
  completed_scans: number;
  running_scans: number;
  findings: number;
  open_findings: number;
  reviewed_findings: number;
  resolved_findings: number;
  blocking_findings: number;
  severity_counts: Record<string, number>;
  status_counts: Record<string, number>;
  disposition_counts: Record<string, number>;
  categories: { category: string; count: number }[];
  recent_scans: SecurityScan[];
  recent_findings: SecurityFinding[];
  disclaimer: string;
}

export interface SecurityScanInput {
  target_type: SecurityTargetType;
  target_id: string;
  checks: string[];
  config?: Record<string, unknown>;
  blocking_enabled?: boolean;
  blocking_severity?: SecuritySeverity;
  blocking_reason?: string;
}

export interface FindingUpdate {
  status?: 'open' | 'reviewed' | 'resolved';
  classification?: 'risk' | 'confirmed_vulnerability';
  note?: string;
}

export interface FindingFilters {
  status?: string;
  severity?: string;
  category?: string;
  check?: string;
  scan?: string;
}

@Injectable({ providedIn: 'root' })
export class SecurityService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  catalog(): Observable<SecurityCheckCatalog> {
    return this.http.get<SecurityCheckCatalog>(`${this.base}/security/checks/`);
  }

  dashboard(projectId: string): Observable<SecurityDashboard> {
    return this.http.get<SecurityDashboard>(
      `${this.base}/projects/${projectId}/security/`,
    );
  }

  scans(projectId: string, status = ''): Observable<SecurityScan[]> {
    let params = new HttpParams();
    if (status) {
      params = params.set('status', status);
    }
    return this.http.get<SecurityScan[]>(
      `${this.base}/projects/${projectId}/security/scans/`,
      { params },
    );
  }

  comparison(
    projectId: string,
    baseline: string,
    current: string,
  ): Observable<SecurityScanComparison> {
    return this.http.get<SecurityScanComparison>(
      `${this.base}/projects/${projectId}/security/compare/`,
      { params: new HttpParams().set('baseline', baseline).set('current', current) },
    );
  }

  createScan(projectId: string, input: SecurityScanInput): Observable<SecurityScan> {
    return this.http.post<SecurityScan>(
      `${this.base}/projects/${projectId}/security/scans/`,
      input,
    );
  }

  scan(scanId: string): Observable<SecurityScan> {
    return this.http.get<SecurityScan>(`${this.base}/security-scans/${scanId}/`);
  }

  scanFindings(
    scanId: string,
    filters: FindingFilters = {},
    page = 1,
  ): Observable<Paginated<SecurityFinding>> {
    return this.http.get<Paginated<SecurityFinding>>(
      `${this.base}/security-scans/${scanId}/findings/`,
      { params: this.findingParams(filters).set('page', page) },
    );
  }

  rerun(scanId: string): Observable<SecurityScan> {
    return this.http.post<SecurityScan>(
      `${this.base}/security-scans/${scanId}/rerun/`,
      {},
    );
  }

  findings(
    projectId: string,
    filters: FindingFilters = {},
    page = 1,
  ): Observable<Paginated<SecurityFinding>> {
    return this.http.get<Paginated<SecurityFinding>>(
      `${this.base}/projects/${projectId}/security/findings/`,
      { params: this.findingParams(filters).set('page', page) },
    );
  }

  finding(findingId: string): Observable<SecurityFinding> {
    return this.http.get<SecurityFinding>(
      `${this.base}/security-findings/${findingId}/`,
    );
  }

  updateFinding(findingId: string, input: FindingUpdate): Observable<SecurityFinding> {
    return this.http.patch<SecurityFinding>(
      `${this.base}/security-findings/${findingId}/`,
      input,
    );
  }

  private findingParams(filters: FindingFilters): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, value);
      }
    }
    return params;
  }
}
