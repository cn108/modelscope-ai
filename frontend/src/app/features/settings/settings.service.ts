import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export interface AboutInfo {
  name: string;
  version: string;
  environment: string;
  api_version: string;
  server_time: string;
  database: string;
  features: {
    judge_metrics: boolean;
    otlp_export: boolean;
    observability_retention_days: number;
  };
  links: {
    api_docs: string;
    openapi: string;
    documentation: string;
    support: string;
  };
}

export interface AuditEventRow {
  id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  actor: string | null;
  actor_email: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  about(): Observable<AboutInfo> {
    return this.http.get<AboutInfo>(`${this.base}/about/`);
  }

  accountAudit(): Observable<Paginated<AuditEventRow>> {
    return this.http.get<Paginated<AuditEventRow>>(`${this.base}/auth/audit/`);
  }
}
