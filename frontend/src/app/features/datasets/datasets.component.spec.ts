import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { DatasetsComponent } from './datasets.component';

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
  description: 'Regression cases',
  version: 3,
  record_count: 1,
  created_by: 'user-1',
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const RECORD = {
  id: 'record-1',
  dataset: 'dataset-1',
  position: 1,
  input: 'How do I reset my password?',
  expected_output: 'Use the reset link.',
  context: ['Passwords reset from the login screen.'],
  metadata: {},
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

describe('DatasetsComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DatasetsComponent],
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
    const fixture = TestBed.createComponent(DatasetsComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Create a project first');
  });

  it('loads datasets and renders the selected dataset records', async () => {
    const fixture = TestBed.createComponent(DatasetsComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/workspaces/').flush(page([WORKSPACE]));
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush(page([PROJECT]));
    httpMock
      .expectOne('/api/v1/projects/project-1/datasets/')
      .flush([DATASET]);
    httpMock.expectOne('/api/v1/datasets/dataset-1/').flush(DATASET);
    httpMock
      .expectOne('/api/v1/datasets/dataset-1/records/?page=1')
      .flush(page([RECORD]));

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Datasets');
    expect(text).toContain('Support QA');
    expect(text).toContain('Version 3');
    expect(text).toContain('How do I reset my password?');
    expect(text).toContain('Use the reset link.');
    expect(text).toContain('Import test cases');
  });
});
