import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { EvaluationsComponent } from './evaluations.component';

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

const DATASET = {
  id: 'dataset-1',
  project: 'project-1',
  name: 'Support QA',
  description: '',
  version: 2,
  record_count: 3,
  created_by: 'user-1',
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const PROVIDER = {
  id: 'provider-1',
  project: 'project-1',
  name: 'Local Ollama',
  kind: 'ollama' as const,
  endpoint: 'http://localhost:11434',
  settings: {},
  connection_status: 'connected' as const,
  connection_detail: '',
  last_tested_at: null,
  has_secret: false,
  models: [{ id: 'model-1', model_id: 'llama3.2', display_name: 'Llama 3.2' }],
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const METRICS = {
  metrics: [
    {
      key: 'exact_match',
      label: 'Exact match',
      description: 'Compares against the expected answer.',
      requires_expected_output: true,
      requires_context: false,
      requires_judge: false,
      threshold: null,
      source: 'builtin',
    },
    {
      key: 'faithfulness',
      label: 'Faithfulness',
      description: 'DeepEval judge over the record context.',
      requires_expected_output: false,
      requires_context: true,
      requires_judge: true,
      threshold: 0.5,
      source: 'deepeval',
    },
  ],
};

const EVALUATION = {
  id: 'evaluation-1',
  project: 'project-1',
  dataset: 'dataset-1',
  dataset_name: 'Support QA',
  dataset_version: 2,
  status: 'completed' as const,
  metrics: ['exact_match'],
  parameters: {},
  judge: null,
  total_cases: 3,
  total_results: 3,
  completed_cases: 3,
  failed_cases: 0,
  summary: { totals: { models: 1, cases: 3, succeeded: 3, failed: 0 } },
  review_summary: {
    total_reviews: 0,
    reviewed_results: 0,
    labels: {},
    disagreements: 0,
    agreement_rate: null,
  },
  error: null,
  created_by: 'user-1',
  created_at: '2026-01-03T00:00:00Z',
  started_at: '2026-01-03T00:00:00Z',
  completed_at: '2026-01-03T00:01:00Z',
  models: [
    {
      id: 'eval-model-1',
      position: 0,
      provider: 'provider-1',
      provider_name: 'Local Ollama',
      provider_kind: 'ollama',
      model_id: 'llama3.2',
      parameters: {},
      status: 'completed' as const,
      summary: {
        cases: 3,
        succeeded: 3,
        failed: 0,
        avg_latency_ms: 420,
        total_input_tokens: 30,
        total_output_tokens: 12,
        metric_averages: { exact_match: 0.67 },
        metric_scored_counts: { exact_match: 3 },
      },
      error: null,
    },
  ],
};

const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

describe('EvaluationsComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [EvaluationsComponent],
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
    const fixture = TestBed.createComponent(EvaluationsComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/evaluation-metrics/').flush(METRICS);
    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Create a project first');
  });

  it('renders the run form and the latest evaluation summary', async () => {
    const fixture = TestBed.createComponent(EvaluationsComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/evaluation-metrics/').flush(METRICS);
    httpMock.expectOne('/api/v1/workspaces/').flush(page([WORKSPACE]));
    httpMock.expectOne('/api/v1/projects/?workspace=ws-1').flush(page([PROJECT]));
    httpMock.expectOne('/api/v1/projects/project-1/datasets/').flush([DATASET]);
    httpMock
      .expectOne('/api/v1/projects/project-1/providers/')
      .flush([PROVIDER]);
    httpMock
      .expectOne('/api/v1/projects/project-1/evaluations/')
      .flush([EVALUATION]);
    httpMock.expectOne('/api/v1/evaluations/evaluation-1/').flush(EVALUATION);
    httpMock
      .expectOne('/api/v1/evaluations/evaluation-1/results/?page=1')
      .flush(page([]));

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Evaluations');
    expect(text).toContain('Support QA');
    expect(text).toContain('Exact match');
    expect(text).toContain('llama3.2');
    expect(text).toContain('3 / 3 passed');
    expect(text).toContain('0.67');
    expect(text).toContain('Rerun');
  });
});
