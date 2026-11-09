import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/authentication/auth.service';
import { apiErrorMessage } from '../../shared/api-error';
import { IconComponent, IconName } from '../../shared/ui/icon.component';

type AuthMode = 'login' | 'register';

interface Highlight {
  icon: IconName;
  title: string;
  detail: string;
}

@Component({
  selector: 'msa-login',
  standalone: true,
  imports: [ReactiveFormsModule, IconComponent],
  template: `
    <main class="min-h-screen bg-canvas lg:grid lg:grid-cols-[1.05fr_1fr]">
      <section
        class="relative hidden overflow-hidden bg-navy p-12 text-white lg:flex lg:flex-col lg:justify-between"
      >
        <div class="pointer-events-none absolute inset-0">
          <div
            class="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-brand/40 blur-3xl"
          ></div>
          <div
            class="absolute -bottom-32 right-0 h-96 w-96 rounded-full bg-violet/30 blur-3xl"
          ></div>
        </div>

        <div class="relative">
          <div class="flex items-center gap-3">
            <span
              class="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-violet text-xl font-bold shadow-lg shadow-brand/30"
            >
              M
            </span>
            <span class="leading-tight">
              <span class="block tracking-tight text-lg font-semibold">
                ModelScope AI
              </span>
              <span class="block text-[11px] text-slate-400">
                Evaluate · Monitor · Improve
              </span>
            </span>
          </div>

          <h1 class="mt-16 max-w-md text-4xl font-semibold leading-tight">
            Build better AI with confidence.
          </h1>
          <p class="mt-4 max-w-sm text-sm leading-relaxed text-slate-400">
            One workspace to compare models, track performance and keep your AI
            applications secure.
          </p>

          <ul class="mt-10 space-y-4">
            @for (highlight of highlights; track highlight.title) {
              <li class="flex items-start gap-3">
                <span
                  class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/10 text-emerald-300"
                >
                  <msa-icon name="check" [size]="15" />
                </span>
                <span>
                  <span class="block text-sm font-medium text-white">{{
                    highlight.title
                  }}</span>
                  <span class="block text-xs text-slate-400">{{
                    highlight.detail
                  }}</span>
                </span>
              </li>
            }
          </ul>
        </div>

        <p class="relative text-xs text-slate-500">
          Evaluation &amp; observability platform for AI teams
        </p>
      </section>

      <section
        class="flex min-h-screen items-center justify-center px-5 py-10 sm:px-8"
      >
        <div class="w-full max-w-sm">
          <div class="mb-8 flex items-center gap-3 lg:hidden">
            <span
              class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-violet text-lg font-bold text-white"
            >
              M
            </span>
            <span class="text-base font-semibold tracking-tight">
              ModelScope AI
            </span>
          </div>

          <div class="msa-card p-7 sm:p-8">
            <h2 class="text-xl font-semibold tracking-tight text-ink">
              {{ mode() === 'login' ? 'Welcome back' : 'Create your account' }}
            </h2>
            <p class="mt-1 text-sm text-muted">
              {{
                mode() === 'login'
                  ? 'Sign in to your workspace'
                  : 'Set up your account to start evaluating models'
              }}
            </p>

            <form [formGroup]="form" (ngSubmit)="submit()" class="mt-6 space-y-4">
              <div>
                <label class="msa-label" for="email">Email</label>
                <input
                  id="email"
                  formControlName="email"
                  type="email"
                  autocomplete="email"
                  placeholder="you@company.com"
                  [class.msa-input-error]="
                    form.controls.email.touched && form.controls.email.invalid
                  "
                  class="msa-input"
                />
                @if (form.controls.email.touched && form.controls.email.invalid) {
                  <p class="mt-1 text-xs text-rose-600">
                    Enter a valid email address.
                  </p>
                }
              </div>

              @if (mode() === 'register') {
                <div>
                  <label class="msa-label" for="display_name">Display name</label>
                  <input
                    id="display_name"
                    formControlName="display_name"
                    type="text"
                    autocomplete="name"
                    placeholder="Jane Doe"
                    class="msa-input"
                  />
                </div>
              }

              <div>
                <label class="msa-label" for="password">Password</label>
                <input
                  id="password"
                  formControlName="password"
                  type="password"
                  [attr.autocomplete]="
                    mode() === 'login' ? 'current-password' : 'new-password'
                  "
                  placeholder="••••••••"
                  [class.msa-input-error]="
                    form.controls.password.touched &&
                    form.controls.password.invalid
                  "
                  class="msa-input"
                />
                @if (
                  form.controls.password.touched && form.controls.password.invalid
                ) {
                  <p class="mt-1 text-xs text-rose-600">
                    Passwords need at least 8 characters.
                  </p>
                }
              </div>

              @if (error()) {
                <p
                  class="flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700"
                  role="alert"
                >
                  <msa-icon name="alert" [size]="16" />
                  <span>{{ error() }}</span>
                </p>
              }

              <button
                type="submit"
                [disabled]="submitting()"
                class="msa-btn-primary w-full py-2.5"
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

            <div class="mt-6 flex items-center gap-3">
              <span class="h-px flex-1 bg-line"></span>
              <span class="text-[11px] uppercase tracking-wide text-slate-400">
                {{ mode() === 'login' ? 'New here?' : 'Already registered?' }}
              </span>
              <span class="h-px flex-1 bg-line"></span>
            </div>

            <button
              type="button"
              (click)="toggleMode()"
              class="msa-btn-secondary mt-3 w-full"
            >
              {{ mode() === 'login' ? 'Create an account' : 'Sign in instead' }}
            </button>
          </div>

          <p class="mt-6 text-center text-xs text-slate-400">
            Provider keys are encrypted at rest · Access is scoped per workspace
          </p>
        </div>
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

  readonly highlights: Highlight[] = [
    {
      icon: 'check-circle',
      title: 'Evaluate & compare models',
      detail: 'Side-by-side quality and cost signals',
    },
    {
      icon: 'activity',
      title: 'Monitor performance',
      detail: 'Latency, errors and spend in one view',
    },
    {
      icon: 'shield',
      title: 'Secure your stack',
      detail: 'Workspace roles and encrypted credentials',
    },
  ];

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
