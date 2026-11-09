import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SecurityTestingComponent } from './security-testing.component';

const WORKSPACE = {
  id: 'ws-1',
  name: 'Acme',
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

const CATALOG = {
  categories: [
    {
      key: 'prompt_injection',
      label: 'Prompt injection',
      count: 1,
      cases: [
        {
          key: 'prompt_injection.direct_override',
          name: 'Direct instruction override',
          description: 'A user message tells the model to discard its instruction.',
          technique: 'Direct prompt injection',
          severity: 'high',
          criteria: 'Fails on RED without a refusal; passes on BLUE.',
          limitation: 'Single-turn probe only.',
          references: ['OWASP LLM01'],
        },
      ],
    },
  ],
  case_count: 1,
  detectors: ['instruction_adherence'],
  disclaimer: 'Automated security testing is a detection aid.',
  limitations: ['Single-turn probes only.'],
};

const PROVIDER = {
  id: 'provider-1',
  project: 'project-1',
  name: 'Local Ollama',
  kind: 'ollama',
  endpoint: 'http://localhost:11434',
  settings: {},
  connection_status: 'untested',
  connection_detail: '',
  last_tested_at: null,
  has_secret: false,
  models: [{ id: 'model-1', model_id: 'llama3.2', display_name: 'Llama 3.2' }],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const DASHBOARD = {
  project: 'project-1',
  runs: 1,
  completed_runs: 1,
  failed_runs: 0,
  running_runs: 0,
  tests_performed: 4,
  passed: 3,
  failed: 1,
  inconclusive: 0,
  vulnerabilities: 1,
  decisive: 4,
  pass_rate: 0.75,
  fail_rate: 0.25,
  coverage: 1,
  severity_counts: { info: 0, low: 0, medium: 0, high: 1, critical: 0 },
  highest_severity: 'high',
  categories: [
    {
      category: 'prompt_injection',
      label: 'Prompt injection',
      total: 4,
      passed: 3,
      failed: 1,
      inconclusive: 0,
    },
  ],
  models: [
    {
      provider: 'provider-1',
      provider_name: 'Local Ollama',
      provider_kind: 'ollama',
      model_id: 'llama3.2',
      total: 4,
      passed: 3,
      failed: 1,
      inconclusive: 0,
      vulnerabilities: 1,
      errors: 0,
      decisive: 4,
      pass_rate: 0.75,
      fail_rate: 0.25,
      coverage: 1,
      severity_counts: { info: 0, low: 0, medium: 0, high: 1, critical: 0 },
      highest_severity: 'high',
      categories: [],
    },
  ],
  recent_runs: [],
  recent_failures: [],
  disclaimer: 'Automated security testing is a detection aid, not a guarantee.',
  limitations: ['Single-turn probes only.'],
};

const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

describe('SecurityTestingComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [SecurityTestingComponent],
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
    const fixture = TestBed.createComponent(SecurityTestingComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/security-testing/catalog/').flush(CATALOG);
    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Create a project first');
  });

  it('renders the testing dashboard, model comparison and history', async () => {
    const fixture = TestBed.createComponent(SecurityTestingComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/security-testing/catalog/').flush(CATALOG);
    httpMock.expectOne('/api/v1/workspaces/').flush(page([WORKSPACE]));
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush(page([PROJECT]));
    httpMock
      .expectOne('/api/v1/projects/project-1/providers/')
      .flush([PROVIDER]);
    httpMock
      .expectOne('/api/v1/projects/project-1/security-testing/')
      .flush(DASHBOARD);
    httpMock
      .expectOne('/api/v1/projects/project-1/security-testing/runs/')
      .flush([]);

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('AI Security Testing');
    expect(text).toContain('Tests performed');
    expect(text).toContain('Vulnerabilities');
    expect(text).toContain('Model security comparison');
    expect(text).toContain('llama3.2');
    expect(text).toContain('Results by attack category');
    expect(text).toContain('Test run history');
    expect(text).toContain('reviewed cases');
  });
});
