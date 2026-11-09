import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { DashboardComponent } from './dashboard.component';

@Component({ selector: 'msa-root', template: '' })
class StubRoot {}

const WORKSPACE = {
  id: 'ws-1',
  name: 'Acme Corp',
  owner: 'user-1',
  settings: {},
  role: 'owner',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('DashboardComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function flushEmptyWorkspaces(): void {
    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 0, next: null, previous: null, results: [] });
  }

  it('renders healthy status from the API', async () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const req = httpMock.expectOne('/api/v1/health/');
    req.flush({ status: 'ok', service: 'modelscope-api', database: { status: 'ok', engine: 'postgresql' } });
    flushEmptyWorkspaces();
    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('modelscope-api');
    expect(text).toContain('ok');
  });

  it('shows an error state when the API is unreachable', async () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/health/').flush('boom', { status: 0, statusText: 'Down' });
    flushEmptyWorkspaces();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('API unreachable');
  });

  it('summarises workspace projects and members', async () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    httpMock
      .expectOne('/api/v1/health/')
      .flush({ status: 'ok', service: 'modelscope-api', database: { status: 'ok', engine: 'postgresql' } });
    httpMock
      .expectOne('/api/v1/workspaces/')
      .flush({ count: 1, next: null, previous: null, results: [WORKSPACE] });
    httpMock
      .expectOne('/api/v1/projects/?workspace=ws-1')
      .flush({ count: 2, next: null, previous: null, results: [] });
    httpMock
      .expectOne('/api/v1/workspaces/ws-1/members/')
      .flush({ count: 3, next: null, previous: null, results: [] });

    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Acme Corp');
    expect(text).toContain('2 projects');
    expect(text).toContain('3 members');
    expect(text).toContain('Workspace breakdown');
  });
});
