import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { LoginComponent } from './login.component';

describe('LoginComponent', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
  });

  it('renders the sign-in form', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const text: string = fixture.nativeElement.textContent;
    expect(text).toContain('Welcome back');
    expect(text).toContain('Sign in');
    expect(fixture.nativeElement.querySelector('#email')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('#password')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('#display_name')).toBeFalsy();
  });

  it('switches to registration and reveals the display name field', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    fixture.componentInstance.toggleMode();
    fixture.detectChanges();

    expect(fixture.componentInstance.mode()).toBe('register');
    expect(fixture.nativeElement.textContent).toContain('Create your account');
    expect(fixture.nativeElement.querySelector('#display_name')).toBeTruthy();
  });

  it('does not submit an invalid form', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    fixture.componentInstance.form.patchValue({ email: 'not-an-email' });
    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(fixture.componentInstance.submitting()).toBe(false);
    expect(fixture.componentInstance.form.controls.email.touched).toBe(true);
  });
});
