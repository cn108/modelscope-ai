import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AuthResponse, User } from '../../shared/models/auth.model';
import {
  clearSession,
  persistSession,
  persistUser,
  readAccessToken,
  readRefreshToken,
  readStoredUser,
} from './session';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly base = `${environment.apiBaseUrl}/auth`;

  readonly user = signal<User | null>(readStoredUser());
  readonly accessToken = signal<string | null>(readAccessToken());
  readonly isAuthenticated = computed(() => this.accessToken() !== null);

  login(email: string, password: string): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/login/`, { email, password })
      .pipe(tap((response) => this.applySession(response)));
  }

  register(
    email: string,
    password: string,
    displayName: string,
  ): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/register/`, {
        email,
        password,
        display_name: displayName,
      })
      .pipe(tap((response) => this.applySession(response)));
  }

  me(): Observable<User> {
    return this.http.get<User>(`${this.base}/me/`).pipe(
      tap((user) => {
        this.user.set(user);
        persistUser(user);
      }),
    );
  }

  updateProfile(input: {
    display_name?: string;
    preferences?: Record<string, unknown>;
  }): Observable<User> {
    return this.http.patch<User>(`${this.base}/me/`, input).pipe(
      tap((user) => {
        this.user.set(user);
        persistUser(user);
      }),
    );
  }

  changePassword(
    currentPassword: string,
    newPassword: string,
  ): Observable<{ detail: string; refresh_tokens_revoked: number }> {
    return this.http.post<{ detail: string; refresh_tokens_revoked: number }>(
      `${this.base}/change-password/`,
      {
        current_password: currentPassword,
        new_password: newPassword,
      },
    );
  }

  landingRoute(): string {
    const page = this.user()?.preferences?.landing_page;
    return page === 'workspaces' || page === 'playground'
      ? `/${page}`
      : '/dashboard';
  }

  logout(): void {
    const refresh = readRefreshToken();
    const access = this.accessToken();
    if (refresh && access) {
      this.http
        .post(
          `${this.base}/logout/`,
          { refresh },
          { headers: { Authorization: `Bearer ${access}` } },
        )
        .subscribe({ error: () => undefined });
    }
    clearSession();
    this.user.set(null);
    this.accessToken.set(null);
    void this.router.navigate(['/login']);
  }

  private applySession(response: AuthResponse): void {
    persistSession(response);
    this.user.set(response.user);
    this.accessToken.set(response.tokens.access);
  }
}
