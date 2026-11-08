/** Typed API response models (specification section 6). */

export interface ComponentStatus {
  status: 'ok' | 'error' | 'degraded';
  detail?: string;
}

export interface DatabaseStatus extends ComponentStatus {
  engine?: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  database: DatabaseStatus;
}

export interface WorkerHealthResponse {
  status: 'ok' | 'degraded';
  broker: ComponentStatus;
  worker?: { status: 'ok' | 'error'; echo?: string; detail?: string };
}
