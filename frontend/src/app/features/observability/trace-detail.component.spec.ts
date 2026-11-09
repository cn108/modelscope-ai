import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';

import { TraceDetailComponent } from './trace-detail.component';

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
  otel_trace_id: '4bf92f3577b34da6a3ce929d0e0e4736',
  request_preview: 'Say hello.',
  link: { source: 'playground', execution_id: 'execution-1', result_id: 'result-1' },
  request: {
    kind: 'playground',
    system_prompt: 'Be terse.',
    user_prompt: 'Say hello.',
    parameters: { max_tokens: 64 },
    prompt_version: 2,
    execution_id: 'execution-1',
  },
  response: 'Hello there.',
  attributes: {},
  spans: [
    {
      id: 'span-1',
      parent: null,
      sequence: 0,
      name: 'provider.prepare',
      kind: 'internal',
      status: 'ok',
      started_at: '2026-01-03T10:00:00Z',
      ended_at: '2026-01-03T10:00:00Z',
      duration_ms: 12,
      attributes: { 'provider.kind': 'ollama' },
      error: null,
    },
    {
      id: 'span-2',
      parent: null,
      sequence: 1,
      name: 'provider.generate',
      kind: 'client',
      status: 'ok',
      started_at: '2026-01-03T10:00:00Z',
      ended_at: '2026-01-03T10:00:01Z',
      duration_ms: 620,
      attributes: { 'gen_ai.usage.input_tokens': 12 },
      error: null,
    },
    {
      id: 'span-3',
      parent: null,
      sequence: 2,
      name: 'metrics.evaluate',
      kind: 'internal',
      status: 'ok',
      started_at: '2026-01-03T10:00:01Z',
      ended_at: '2026-01-03T10:00:01Z',
      duration_ms: 60,
      attributes: { metrics: ['exact_match'] },
      error: null,
    },
    {
      id: 'span-4',
      parent: 'span-3',
      sequence: 3,
      name: 'metrics.exact_match',
      kind: 'internal',
      status: 'ok',
      started_at: '2026-01-03T10:00:01Z',
      ended_at: '2026-01-03T10:00:01Z',
      duration_ms: 30,
      attributes: { metric: 'exact_match', score: 1 },
      error: null,
    },
  ],
};

describe('TraceDetailComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [TraceDetailComponent],
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => 'trace-1' } } },
        },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders request, response and nested spans', async () => {
    const fixture = TestBed.createComponent(TraceDetailComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/observability/traces/trace-1/').flush(TRACE);
    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Local Ollama');
    expect(text).toContain('llama3.2');
    expect(text).toContain('Say hello.');
    expect(text).toContain('Hello there.');
    expect(text).toContain('Request');
    expect(text).toContain('Response');
    expect(text).toContain('Spans');
    expect(text).toContain('provider.generate');
    expect(text).toContain('metrics.evaluate');
    expect(text).toContain('metrics.exact_match');
    expect(text).toContain('620 ms');
    expect(text).toContain('Unavailable');
    expect(text).toContain('4bf92f3577b34da6a3ce929d0e0e4736');
  });
});
