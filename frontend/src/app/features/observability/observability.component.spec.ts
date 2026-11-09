import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ObservabilityComponent } from './observability.component';

const WORKSPACE = {
  id: 'ws-1',
  name: 'Acme Corp',
  owner: 'user-1',
  settings: {},
  role: 'owner',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const PROJECT = {
  id: 'project-1',
  workspace: 'ws-1',
  name: 'Support AI',
  description: '',
  created_by: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const TRACE = {
  id: 'trace-1',
  project: 'project-1',
  source: 'playground' as const,
  source_label: 'Playground',
  role: 'model' as const,
  status: 'succeeded' as const,
  provider: 'provider-1',
  provider_name: 'Local Ollama',
  provider_kind: 'ollama',
  model_id: 'llama3.2',
  started_at: '2026-01-03T10:00:00Z',
  ended_at: '2026-01-03T10:00:01Z',
  duration_ms: 840,
  provider_latency_ms: 620,
  input_tokens: 12,
  output_tokens: 8,
  estimated_cost: null,
  cost_currency: '',
  cost_status: 'unavailable' as const,
  cost_detail: 'No pricing is configured for ollama:llama3.2.',
  error: null,
  otel_trace_id: '',
  request_preview: 'Say hello.',
  link: { source: 'playground', execution_id: 'execution-1', result_id: 'result-1' },
};

const DASHBOARD = {
  project: 'project-1',
  totals: {
    calls: 8,
    succeeded: 7,
    failed: 1,
    avg_latency_ms: 640,
    avg_duration_ms: 700,
    input_tokens: 96,
    output_tokens: 48,
    token_calls: 8,
    estimated_cost_calls: 0,
    unavailable_cost_calls: 8,
    first_seen: '2026-01-03T10:00:00Z',
    last_seen: '2026-01-03T11:00:00Z',
    roles: { model: 6, judge: 2 },
  },
  costs: [],
  cost_status: 'unavailable' as const,
  cost_detail: 'No pricing is configured and/or tokens were not reported.',
  models: [
    {
      provider_id: 'provider-1',
      provider_name: 'Local Ollama',
      provider_kind: 'ollama',
      model_id: 'llama3.2',
      count: 6,
      succeeded: 5,
      failed: 1,
      avg_latency_ms: 640,
      avg_duration_ms: 700,
      input_tokens: 72,
      output_tokens: 36,
      token_calls: 6,
      costs: [],
      estimated_calls: 0,
      cost_status: 'unavailable' as const,
      failure_rate: 0.1667,
      roles: { model: 6 },
      last_seen: '2026-01-03T11:00:00Z',
    },
    {
      provider_id: 'provider-1',
      provider_name: 'Local Ollama',
      provider_kind: 'ollama',
      model_id: 'judge-model',
      count: 2,
      succeeded: 2,
      failed: 0,
      avg_latency_ms: 400,
      avg_duration_ms: 420,
      input_tokens: 24,
      output_tokens: 12,
      token_calls: 2,
      costs: [],
      estimated_calls: 0,
      cost_status: 'unavailable' as const,
      failure_rate: 0,
      roles: { judge: 2 },
      last_seen: '2026-01-03T11:00:00Z',
    },
  ],
  providers: [
    {
      provider_id: 'provider-1',
      provider_name: 'Local Ollama',
      provider_kind: 'ollama',
      count: 8,
      succeeded: 7,
      failed: 1,
      avg_latency_ms: 640,
      avg_duration_ms: 700,
      input_tokens: 96,
      output_tokens: 48,
      token_calls: 8,
      costs: [],
      estimated_calls: 0,
      cost_status: 'unavailable' as const,
      failure_rate: 0.125,
      roles: { model: 6, judge: 2 },
      last_seen: '2026-01-03T11:00:00Z',
    },
  ],
  trend: [
    {
      day: '2026-01-03',
      count: 8,
      succeeded: 7,
      failed: 1,
      avg_latency_ms: 640,
      input_tokens: 96,
      output_tokens: 48,
      costs: [],
    },
  ],
  errors: [{ category: 'network_error', count: 1 }],
  slowest: [TRACE],
  rollups: {
    enabled: true,
    through: '2026-01-02',
    from: '2026-01-02',
    to: '2026-01-02',
    retention_days: 30,
  },
  facets: {
    providers: [{ id: 'provider-1', name: 'Local Ollama', kind: 'ollama' }],
    models: ['judge-model', 'llama3.2'],
  },
  telemetry: {
    enabled: true,
    exported: false,
    detail: 'Spans are recorded in-process; no OTLP endpoint is configured.',
  },
};

const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

describe('ObservabilityComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ObservabilityComponent],
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('prompts the user to create a project when none exist', async () => {
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Create a project first');
  });

  it('renders totals, usage, trend and recent traces', async () => {
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/workspaces/').flush(page([WORKSPACE]));
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush(page([PROJECT]));
    httpMock
      .expectOne('/api/v1/projects/project-1/observability/')
      .flush(DASHBOARD);
    httpMock
      .expectOne('/api/v1/projects/project-1/observability/traces/?page=1')
      .flush(page([TRACE]));

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Observability');
    expect(text).toContain('Total executions');
    expect(text).toContain('8');
    expect(text).toContain('Succeeded / failed');
    expect(text).toContain('Average latency');
    expect(text).toContain('640 ms');
    expect(text).toContain('Tokens');
    expect(text).toContain('Estimated cost');
    expect(text).toContain('Unavailable');
    expect(text).toContain('Execution trend');
    expect(text).toContain('Model usage');
    expect(text).toContain('llama3.2');
    expect(text).toContain('Provider usage');
    expect(text).toContain('network_error');
    expect(text).toContain('Recent traces');
    expect(text).toContain('Rollups through 2026-01-02');
    expect(text).toContain('Say hello.');
  });
});
