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

interface SoonItem {
  label: string;
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
          class="fixed inset-0 z-30 bg-navy/40 backdrop-blur-sm lg:hidden"
          (click)="closeMobile()"
        ></div>
      }

      <aside
        class="fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col bg-navy text-slate-400 transition-transform duration-200 lg:translate-x-0"
        [class]="mobileOpen() ? 'translate-x-0' : '-translate-x-full'"
      >
        <div class="flex items-center gap-3 px-5 pb-4 pt-5">
          <span
            class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-violet text-lg font-bold text-white shadow-lg shadow-brand/30"
          >
            M
          </span>
          <span class="leading-tight">
            <span class="block tracking-tight text-[15px] font-semibold text-white">
              ModelScope AI
            </span>
            <span class="block text-[11px] text-slate-500">
              Evaluate · Monitor
            </span>
          </span>
          <button
            type="button"
            class="ml-auto rounded-lg p-1.5 text-slate-500 hover:bg-white/10 hover:text-white lg:hidden"
            title="Close navigation"
            (click)="closeMobile()"
          >
            <msa-icon name="close" [size]="16" />
          </button>
        </div>

        <nav class="flex-1 overflow-y-auto px-3 pb-4">
          <p
            class="px-3 pb-2 pt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-600"
          >
            Workspace
          </p>
          @for (item of navItems; track item.path) {
            <a
              [routerLink]="item.path"
              routerLinkActive="bg-brand text-white shadow-sm shadow-brand/30"
              class="mb-1 flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
              (click)="closeMobile()"
            >
              <msa-icon [name]="item.icon" [size]="17" />
              <span>{{ item.label }}</span>
            </a>
          }

          <p
            class="px-3 pb-2 pt-5 text-[10px] font-semibold uppercase tracking-widest text-slate-600"
          >
            Coming next
          </p>
          @for (item of soonItems; track item.label) {
            <div
              class="mb-1 flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] text-slate-600"
              [attr.title]="item.label + ' arrives in a later milestone'"
            >
              <msa-icon [name]="item.icon" [size]="17" />
              <span>{{ item.label }}</span>
              <span
                class="ml-auto rounded-full bg-white/5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-500"
              >
                Soon
              </span>
            </div>
          }
        </nav>

        <div class="border-t border-navy-line px-3 py-3">
          <div class="flex items-center gap-3 rounded-xl px-2 py-2">
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-xs font-semibold text-white"
            >
              {{ initials() }}
            </span>
            <span class="min-w-0 flex-1 leading-tight">
              <span class="block truncate text-[13px] font-medium text-white">
                {{ displayName() }}
              </span>
              <span class="block truncate text-[11px] text-slate-500">
                {{ email() }}
              </span>
            </span>
            <button
              type="button"
              class="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-white/10 hover:text-white"
              title="Sign out"
              (click)="logout()"
            >
              <msa-icon name="logout" [size]="16" />
            </button>
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
          <span
            class="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-[11px] font-semibold text-white"
          >
            {{ initials() }}
          </span>
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

  readonly navItems: NavItem[] = [
    { label: 'Dashboard', path: '/dashboard', icon: 'grid' },
    { label: 'Workspaces', path: '/workspaces', icon: 'layers' },
  ];

  readonly soonItems: SoonItem[] = [
    { label: 'Projects', icon: 'folder' },
    { label: 'Providers', icon: 'plug' },
    { label: 'Playground', icon: 'play' },
    { label: 'Datasets', icon: 'database' },
    { label: 'Evaluations', icon: 'check-circle' },
    { label: 'Observability', icon: 'activity' },
    { label: 'Security', icon: 'shield' },
    { label: 'Settings', icon: 'gear' },
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
