import { Component, computed, inject, signal } from '@angular/core';
import {
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';

import { AuthService } from '../../core/authentication/auth.service';
import { IconComponent, IconName } from '../../shared/ui/icon.component';

interface NavItem {
  label: string;
  path: string;
  icon: IconName;
}

@Component({
  selector: 'msa-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconComponent],
  template: `
    <div class="min-h-screen bg-canvas">
      @if (mobileOpen()) {
        <div
          class="fixed inset-0 z-30 bg-navy/30 backdrop-blur-sm lg:hidden"
          aria-hidden="true"
          (click)="closeMobile()"
        ></div>
      }

      <aside
        class="fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-line bg-[#f7f7f8] transition-transform duration-200 lg:translate-x-0"
        [class]="mobileOpen() ? 'translate-x-0' : '-translate-x-full'"
      >
        <div class="flex h-16 items-center gap-3 px-4">
          <span
            class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-violet text-base font-bold text-white shadow-sm shadow-brand/20"
          >
            M
          </span>
          <span class="leading-tight">
            <span class="block text-[14px] font-semibold tracking-tight text-ink">
              ModelScope AI
            </span>
            <span class="block text-[10px] text-slate-400">
              Evaluate · Monitor · Improve
            </span>
          </span>
          <button
            type="button"
            class="msa-icon-btn ml-auto lg:hidden"
            title="Close navigation"
            aria-label="Close navigation"
            (click)="closeMobile()"
          >
            <msa-icon name="close" [size]="16" />
          </button>
        </div>

        <nav class="flex-1 overflow-y-auto px-3 pb-4" aria-label="Main navigation">
          <p
            class="px-3 pb-2 pt-3 text-[10px] font-semibold uppercase tracking-widest text-slate-400"
          >
            Workspace
          </p>
          @for (item of primaryNav; track item.path) {
            <a
              [routerLink]="item.path"
              routerLinkActive="bg-white text-ink shadow-sm ring-1 ring-line/80"
              class="mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-slate-600 transition-colors hover:bg-white/70 hover:text-ink"
              (click)="closeMobile()"
            >
              <msa-icon [name]="item.icon" [size]="17" class="shrink-0" />
              <span>{{ item.label }}</span>
            </a>
          }

          <p
            class="px-3 pb-2 pt-6 text-[10px] font-semibold uppercase tracking-widest text-slate-400"
          >
            Workspace management
          </p>
          @for (item of secondaryNav; track item.path) {
            <a
              [routerLink]="item.path"
              routerLinkActive="bg-white text-ink shadow-sm ring-1 ring-line/80"
              class="mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-slate-600 transition-colors hover:bg-white/70 hover:text-ink"
              (click)="closeMobile()"
            >
              <msa-icon [name]="item.icon" [size]="17" class="shrink-0" />
              <span>{{ item.label }}</span>
            </a>
          }
        </nav>

        <div class="border-t border-line p-3">
          <div class="rounded-xl bg-white p-2 ring-1 ring-line/80">
            <div class="flex items-center gap-3 px-1 py-1">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-[11px] font-semibold text-white"
              >
                {{ initials() }}
              </span>
              <span class="min-w-0 flex-1 leading-tight">
                <span class="block truncate text-[13px] font-medium text-ink">
                  {{ displayName() }}
                </span>
                <span class="block truncate text-[11px] text-slate-400">
                  {{ email() }}
                </span>
              </span>
              <button
                type="button"
                class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-canvas hover:text-ink"
                title="Sign out"
                aria-label="Sign out"
                (click)="logout()"
              >
                <msa-icon name="logout" [size]="16" />
              </button>
            </div>
            <a
              routerLink="/settings"
              routerLinkActive="text-brand"
              class="mt-1 flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] font-medium text-slate-500 transition-colors hover:bg-canvas hover:text-ink"
              (click)="closeMobile()"
            >
              <msa-icon name="gear" [size]="15" />
              Settings
              <msa-icon name="arrow-right" [size]="12" class="ml-auto" />
            </a>
          </div>
        </div>
      </aside>

      <div class="flex min-h-screen flex-col lg:pl-[264px]">
        <header
          class="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-white/90 px-4 py-3 backdrop-blur lg:hidden"
        >
          <button
            type="button"
            class="msa-icon-btn"
            title="Open navigation"
            aria-label="Open navigation"
            (click)="mobileOpen.set(true)"
          >
            <msa-icon name="menu" [size]="18" />
          </button>
          <span class="flex items-center gap-2 text-sm font-semibold">
            <span
              class="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-violet text-[11px] font-bold text-white"
            >
              M
            </span>
            ModelScope AI
          </span>
          <a
            routerLink="/settings"
            class="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-[11px] font-semibold text-white"
            [attr.aria-label]="'Account settings for ' + displayName()"
          >
            {{ initials() }}
          </a>
        </header>

        <main class="flex-1">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
})
export class ShellComponent {
  private readonly auth = inject(AuthService);

  readonly mobileOpen = signal(false);

  readonly primaryNav: NavItem[] = [
    { label: 'Dashboard', path: '/dashboard', icon: 'grid' },
    { label: 'Workspaces', path: '/workspaces', icon: 'layers' },
    { label: 'Playground', path: '/playground', icon: 'play' },
    { label: 'Datasets', path: '/datasets', icon: 'database' },
    { label: 'Evaluations', path: '/evaluations', icon: 'check-circle' },
    { label: 'Observability', path: '/observability', icon: 'activity' },
    { label: 'Security', path: '/security', icon: 'shield' },
    { label: 'AI Testing', path: '/security-testing', icon: 'shield' },
    { label: 'Analytics', path: '/analytics', icon: 'chart' },
  ];

  readonly secondaryNav: NavItem[] = [
    { label: 'Settings', path: '/settings', icon: 'gear' },
  ];

  readonly displayName = computed(
    () =>
      this.auth.user()?.display_name?.trim() ||
      this.auth.user()?.email ||
      'Signed in',
  );

  readonly email = computed(() => this.auth.user()?.email ?? '');

  readonly initials = computed(() => {
    const source = this.displayName();
    const parts = source.split(/[\s@._-]+/).filter(Boolean);
    const letters =
      parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
    return letters.toUpperCase();
  });

  closeMobile(): void {
    this.mobileOpen.set(false);
  }

  logout(): void {
    this.auth.logout();
  }
}
