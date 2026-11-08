import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { HealthResponse, WorkerHealthResponse } from '../../shared/models/health.model';

/**
 * Centralised typed API layer (specification section 6).
 * Components must not call HttpClient directly.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  readonly base = environment.apiBaseUrl;

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.base}/health/`);
  }

  getWorkerHealth(probe = false): Observable<WorkerHealthResponse> {
    const url = `${this.base}/health/worker/${probe ? '?probe=1' : ''}`;
    return this.http.get<WorkerHealthResponse>(url);
  }
}
