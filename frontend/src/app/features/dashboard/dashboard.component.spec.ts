import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient, withFetch } from '@angular/common/http';

import { DashboardComponent } from './dashboard.component';

@Component({ selector: 'msa-root', template: '' })
class StubRoot {}

describe('DashboardComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [provideHttpClient(withFetch()), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders healthy status from the API', async () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const req = httpMock.expectOne('/api/v1/health/');
    req.flush({ status: 'ok', service: 'modelscope-api', database: { status: 'ok', engine: 'postgresql' } });
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
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('API unreachable');
  });
});
