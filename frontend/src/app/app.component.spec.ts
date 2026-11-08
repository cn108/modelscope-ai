import { TestBed } from '@angular/core/testing';
import { RouterOutlet } from '@angular/router';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch } from '@angular/common/http';

import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([]), provideHttpClient(withFetch())],
    }).compileComponents();
  });

  it('creates the app', async () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('renders a router outlet', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('router-outlet')).toBeTruthy();
  });
});
