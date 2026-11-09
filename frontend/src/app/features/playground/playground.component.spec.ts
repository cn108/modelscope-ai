import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PlaygroundComponent } from './playground.component';

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

describe('PlaygroundComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PlaygroundComponent],
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
    const fixture = TestBed.createComponent(PlaygroundComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Create a project first');
  });

  it('renders the composer with providers, prompts and history', async () => {
    const fixture = TestBed.createComponent(PlaygroundComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 1, next: null, previous: null, results: [WORKSPACE] });
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush({ count: 1, next: null, previous: null, results: [PROJECT] });

    httpMock.expectOne('/api/v1/projects/project-1/providers/').flush([PROVIDER]);
    httpMock.expectOne('/api/v1/projects/project-1/prompts/').flush([
      {
        id: 'prompt-1',
        project: 'project-1',
        name: 'Triage',
        description: '',
        current_version: {
          id: 'version-1',
          version_number: 2,
          system_prompt: 'Be terse',
          user_prompt: 'Classify this ticket',
          parameters: { temperature: 0.2 },
          created_by: 'user-1',
          created_at: '2026-01-03T00:00:00Z',
        },
        version_count: 2,
        created_by: 'user-1',
        created_at: '2026-01-03T00:00:00Z',
        updated_at: '2026-01-03T00:00:00Z',
      },
    ]);
    httpMock.expectOne('/api/v1/projects/project-1/executions/').flush([]);

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Playground');
    expect(text).toContain('Local Ollama');
    expect(text).toContain('Triage');
    expect(text).toContain('2 versions');
    expect(text).toContain('No runs yet');
    expect(text).toContain('Run model');
  });
});
