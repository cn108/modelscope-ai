import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';

import { ProviderManagerComponent } from './provider-manager.component';

const PROVIDER = {
  id: 'provider-1',
  project: 'project-1',
  name: 'Production Z.ai',
  kind: 'zai' as const,
  endpoint: '',
  settings: {},
  connection_status: 'error' as const,
  connection_detail: 'Could not reach the provider endpoint.',
  last_tested_at: null,
  has_secret: true,
  created_at: '2026-01-03T00:00:00Z',
  updated_at: '2026-01-03T00:00:00Z',
};

describe('ProviderManagerComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ProviderManagerComponent],
      providers: [provideHttpClient(withFetch()), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders provider cards with connection status', async () => {
    const fixture = TestBed.createComponent(ProviderManagerComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('canManage', true);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/projects/project-1/providers/').flush([PROVIDER]);
    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Production Z.ai');
    expect(text).toContain('Error');
    expect(text).toContain('Could not reach the provider endpoint.');
    expect(text).toContain('Add provider');
  });

  it('shows the empty state and hides management actions for viewers', async () => {
    const fixture = TestBed.createComponent(ProviderManagerComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('canManage', false);
    fixture.detectChanges();

    httpMock.expectOne('/api/v1/projects/project-1/providers/').flush([]);
    fixture.detectChanges();
    await fixture.whenStable();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('No providers configured');
    expect(text).not.toContain('Add provider');
    expect(text).not.toContain('Add your first provider');
  });
});
