import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { WorkspacesComponent } from './workspaces.component';

const WORKSPACE = (id: string, name: string) => ({
  id,
  name,
  owner: 'user-1',
  settings: {},
  role: 'owner',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const PROJECT = {
  id: 'project-1',
  workspace: 'ws-1',
  name: 'Support Assistant',
  description: 'Answers billing questions',
  created_by: 'user-1',
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const PROVIDER = {
  id: 'provider-1',
  project: 'project-1',
  name: 'Local Ollama',
  kind: 'ollama' as const,
  endpoint: 'http://host.docker.internal:11434/api',
  settings: {},
  connection_status: 'connected' as const,
  connection_detail: 'Ollama is reachable.',
  last_tested_at: '2026-01-03T00:00:00Z',
  has_secret: false,
  created_at: '2026-01-03T00:00:00Z',
  updated_at: '2026-01-03T00:00:00Z',
};

function page(results: unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

describe('WorkspacesComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [WorkspacesComponent],
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function flushWorkspaceData(): void {
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush(page([PROJECT]));
    httpMock
      .expectOne('/api/v1/workspaces/ws-1/members/')
      .flush(page([]));
    httpMock
      .expectOne('/api/v1/projects/project-1/providers/')
      .flush([PROVIDER]);
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-2')
      .flush(page([]));
    httpMock
      .expectOne('/api/v1/workspaces/ws-2/members/')
      .flush(page([]));
  }

  it('renders workspace cards and the selected workspace tables', async () => {
    const fixture = TestBed.createComponent(WorkspacesComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush(page([WORKSPACE('ws-1', 'Acme Corp'), WORKSPACE('ws-2', 'TechCorp')]));
    flushWorkspaceData();
    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Acme Corp');
    expect(text).toContain('TechCorp');
    expect(text).toContain('Support Assistant');
    expect(text).toContain('1 provider');
  });

  it('opens the provider panel for a project', async () => {
    const fixture = TestBed.createComponent(WorkspacesComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush(page([WORKSPACE('ws-1', 'Acme Corp'), WORKSPACE('ws-2', 'TechCorp')]));
    flushWorkspaceData();
    fixture.detectChanges();
    await fixture.whenStable();

    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    const trigger = buttons.find((button) =>
      button.textContent?.trim().startsWith('Providers'),
    );
    expect(trigger).toBeTruthy();

    trigger!.click();
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/projects/project-1/providers/')
      .flush([PROVIDER]);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('AI providers');
    expect(fixture.nativeElement.textContent).toContain('Local Ollama');
  });
});
