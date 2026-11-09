import { Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/authentication/auth.service';

@Component({
  selector: 'msa-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    @if (auth.isAuthenticated()) {
      <header class="border-b border-slate-200 bg-white">
        <div
          class="mx-auto flex max-w-6xl items-center justify-between gap-4 p-4"
        >
          <div class="flex items-center gap-5">
            <span class="font-semibold tracking-tight">ModelScope AI</span>
            <nav class="flex gap-3 text-sm text-slate-600">
              <a
                routerLink="/workspaces"
                routerLinkActive="font-medium text-slate-900"
                class="hover:text-slate-900"
                >Workspaces</a
              >
              <a
                routerLink="/status"
                routerLinkActive="font-medium text-slate-900"
                class="hover:text-slate-900"
                >Status</a
              >
            </nav>
          </div>
          <div class="flex items-center gap-3 text-sm">
            <span class="text-slate-500">{{ auth.user()?.email }}</span>
            <button
              type="button"
              (click)="logout()"
              class="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
    }
    <router-outlet />
  `,
})
export class AppComponent implements OnInit {
  readonly auth = inject(AuthService);

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.me().subscribe({ error: () => this.auth.logout() });
    }
  }

  logout(): void {
    this.auth.logout();
  }
}
