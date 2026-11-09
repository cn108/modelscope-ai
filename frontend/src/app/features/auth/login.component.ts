import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/authentication/auth.service';
import { apiErrorMessage } from '../../shared/api-error';

type AuthMode = 'login' | 'register';

@Component({
  selector: 'msa-login',
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <main class="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <section
        class="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <h1 class="text-2xl font-semibold tracking-tight">ModelScope AI</h1>
        <p class="mt-1 text-sm text-slate-500">
          {{
            mode() === 'login'
              ? 'Sign in to your workspace'
              : 'Create your account'
          }}
        </p>

        <form [formGroup]="form" (ngSubmit)="submit()" class="mt-6 space-y-4">
          <label class="block text-sm font-medium text-slate-700">
            Email
            <input
              formControlName="email"
              type="email"
              autocomplete="email"
              class="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </label>

          @if (mode() === 'register') {
            <label class="block text-sm font-medium text-slate-700">
              Display name
              <input
                formControlName="display_name"
                type="text"
                autocomplete="name"
                class="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </label>
          }

          <label class="block text-sm font-medium text-slate-700">
            Password
            <input
              formControlName="password"
              type="password"
              [attr.autocomplete]="
                mode() === 'login' ? 'current-password' : 'new-password'
              "
              class="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </label>

          @if (error()) {
            <p class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {{ error() }}
            </p>
          }

          <button
            type="submit"
            [disabled]="submitting()"
            class="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {{
              submitting()
                ? 'Please wait…'
                : mode() === 'login'
                  ? 'Sign in'
                  : 'Create account'
            }}
          </button>
        </form>

        <button
          type="button"
          (click)="toggleMode()"
          class="mt-4 text-sm text-slate-500 hover:text-slate-900"
        >
          {{
            mode() === 'login'
              ? 'Need an account? Register'
              : 'Already registered? Sign in'
          }}
        </button>
      </section>
    </main>
  `,
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly mode = signal<AuthMode>('login');
  readonly error = signal<string | null>(null);
  readonly submitting = signal(false);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    display_name: [''],
  });

  toggleMode(): void {
    this.mode.update((mode) => (mode === 'login' ? 'register' : 'login'));
    this.error.set(null);
  }

  submit(): void {
    this.error.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { email, password, display_name } = this.form.getRawValue();
    this.submitting.set(true);
    const request =
      this.mode() === 'login'
        ? this.auth.login(email, password)
        : this.auth.register(email, password, display_name);

    request.subscribe({
      next: () => {
        this.submitting.set(false);
        void this.router.navigate(['/workspaces']);
      },
      error: (error: unknown) => {
        this.submitting.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }
}
