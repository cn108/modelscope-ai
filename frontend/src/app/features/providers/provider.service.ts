import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type ProviderKind = 'zai' | 'ollama';

export interface ProviderConfig {
  id: string;
  project: string;
  name: string;
  kind: ProviderKind;
  endpoint: string;
  settings: Record<string, unknown>;
  connection_status: 'untested' | 'connected' | 'error';
  connection_detail: string;
  last_tested_at: string | null;
  has_secret: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderModel {
  id: string;
  provider: string;
  model_id: string;
  display_name: string;
  defaults: Record<string, unknown>;
  created_at: string;
}

export interface ProviderInput {
  name: string;
  kind: ProviderKind;
  endpoint?: string;
  settings?: Record<string, unknown>;
  api_key?: string;
}

@Injectable({ providedIn: 'root' })
export class ProviderService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  list(projectId: string): Observable<ProviderConfig[]> {
    return this.http.get<ProviderConfig[]>(`${this.base}/projects/${projectId}/providers/`);
  }

  create(projectId: string, input: ProviderInput): Observable<ProviderConfig> {
    return this.http.post<ProviderConfig>(`${this.base}/projects/${projectId}/providers/`, input);
  }

  test(providerId: string): Observable<{ ok: boolean; status: string; detail: string }> {
    return this.http.post<{ ok: boolean; status: string; detail: string }>(
      `${this.base}/providers/${providerId}/test/`,
      {},
    );
  }

  models(providerId: string): Observable<ProviderModel[]> {
    return this.http.get<ProviderModel[]>(`${this.base}/providers/${providerId}/models/`);
  }

  delete(providerId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/providers/${providerId}/`);
  }
}
