import { JsonPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin, of, catchError } from 'rxjs';

import { AuthService } from '../../core/authentication/auth.service';
import { apiErrorMessage } from '../../shared/api-error';
import { UserPreferences } from '../../shared/models/auth.model';
import { Membership, Project, Workspace, WorkspaceRole } from '../../shared/models/workspace.model';
import { IconComponent, IconName } from '../../shared/ui/icon.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';
import { ProjectService } from '../projects/project.service';
import { ProviderManagerComponent } from '../providers/provider-manager.component';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  AboutInfo,
  AuditEventRow,
  SettingsService,
} from './settings.service';

type SettingsSection =
  | 'general'
  | 'profile'
  | 'workspace'
  | 'team'
  | 'providers'
  | 'security'
  | 'audit'
  | 'about';

interface SectionItem {
  key: SettingsSection;
  label: string;
  detail: string;
  icon: IconName;
}

const SECTIONS: SectionItem[] = [
  { key: 'general', label: 'General', detail: 'Preferences', icon: 'grid' },
  { key: 'profile', label: 'Profile & account', detail: 'Identity', icon: 'users' },
  { key: 'workspace', label: 'Workspace', detail: 'Name and defaults', icon: 'layers' },
  { key: 'team', label: 'Team & permissions', detail: 'Members and roles', icon: 'shield' },
  { key: 'providers', label: 'AI providers & models', detail: 'Connections', icon: 'plug' },
  { key: 'security', label: 'Security & privacy', detail: 'Password and data', icon: 'check-circle' },
  { key: 'audit', label: 'Audit logs', detail: 'Recent activity', icon: 'activity' },
  { key: 'about', label: 'About ModelScope AI', detail: 'Build information', icon: 'server' },
];

const DEFAULT_TIMEZONES = [
  'UTC',
  'Africa/Accra',
  'Africa/Cairo',
  'Africa/Johannesburg',
  'America/Chicago',
  'America/Los_Angeles',
  'America/New_York',
  'America/Sao_Paulo',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/Berlin',
  'Europe/London',
  'Europe/Paris',
];

@Component({
  selector: 'msa-settings',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    JsonPipe,
    IconComponent,
    LocalDatePipe,
    ProviderManagerComponent,
  ],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Settings</h1>
          <p class="msa-sub">
            Manage your account, workspace and the way ModelScope AI behaves for you.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          @if (workspaces().length) {
            <label class="flex items-center gap-2 text-xs text-muted">
              <span class="font-medium">Workspace</span>
              <select
                class="msa-input min-w-[190px]"
                [value]="selectedWorkspaceId()"
                (change)="selectWorkspace($any($event.target).value)"
                aria-label="Settings workspace"
              >
                @for (workspace of workspaces(); track workspace.id) {
                  <option [value]="workspace.id">{{ workspace.name }}</option>
                }
              </select>
            </label>
          }
          <span class="msa-badge bg-slate-50 text-slate-500">
            {{ auth.user()?.email }}
          </span>
        </div>
      </header>

      @if (notice()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700"
          role="status"
        >
          <msa-icon name="check-circle" [size]="16" />
          <span>{{ notice() }}</span>
        </p>
      }
      @if (error()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
          role="alert"
        >
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }

      <div class="mt-6 grid gap-6 lg:grid-cols-[236px_1fr]">
        <nav
          class="msa-card h-fit overflow-x-auto p-2 lg:sticky lg:top-6"
          aria-label="Settings sections"
        >
          <div class="flex gap-1 lg:flex-col">
            @for (section of sections; track section.key) {
              <button
                type="button"
                class="flex min-w-[190px] items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors lg:min-w-0 lg:w-full"
                [class]="
                  active() === section.key
                    ? 'bg-brand-soft text-brand'
                    : 'text-slate-600 hover:bg-canvas hover:text-ink'
                "
                [attr.aria-current]="active() === section.key ? 'page' : null"
                (click)="selectSection(section.key)"
              >
                <msa-icon [name]="section.icon" [size]="17" class="shrink-0" />
                <span class="min-w-0">
                  <span class="block truncate text-[13px] font-medium">
                    {{ section.label }}
                  </span>
                  <span class="block truncate text-[10px] text-slate-400">
                    {{ section.detail }}
                  </span>
                </span>
              </button>
            }
          </div>
        </nav>

        <div class="min-w-0">
          @if (loading()) {
            <div class="msa-card p-6">
              <div class="msa-skeleton h-5 w-40"></div>
              <div class="msa-skeleton mt-4 h-10 w-full"></div>
              <div class="msa-skeleton mt-2 h-10 w-full"></div>
            </div>
          } @else {
            @switch (active()) {
              @case ('general') {
                <section class="msa-card">
                  <div class="msa-card-header">
                    <div>
                      <h2 class="msa-section-title">General preferences</h2>
                      <p class="text-xs text-muted">
                        These choices apply to your account on every device.
                      </p>
                    </div>
                  </div>
                  <form
                    [formGroup]="generalForm"
                    (ngSubmit)="saveGeneral()"
                    class="space-y-5 p-5 sm:p-6"
                  >
                    <div class="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label class="msa-label" for="settings-timezone">Time zone</label>
                        <input
                          id="settings-timezone"
                          formControlName="timezone"
                          list="settings-timezones"
                          class="msa-input"
                          placeholder="Europe/London"
                        />
                        <datalist id="settings-timezones">
                          @for (zone of timezones; track zone) {
                            <option [value]="zone"></option>
                          }
                        </datalist>
                        <p class="mt-1 text-[11px] text-slate-400">
                          Dates and times are shown in this zone.
                        </p>
                      </div>
                      <div>
                        <label class="msa-label" for="settings-date-format">Date and time format</label>
                        <select
                          id="settings-date-format"
                          formControlName="date_format"
                          class="msa-input"
                        >
                          <option value="medium">Medium — 9 Nov 2026, 14:30</option>
                          <option value="short">Short — 09/11/26, 14:30</option>
                          <option value="iso">ISO — 2026-11-09 14:30</option>
                        </select>
                      </div>
                      <div>
                        <label class="msa-label" for="settings-default-workspace">Default workspace</label>
                        <select
                          id="settings-default-workspace"
                          formControlName="default_workspace"
                          class="msa-input"
                        >
                          <option value="">No default</option>
                          @for (workspace of workspaces(); track workspace.id) {
                            <option [value]="workspace.id">{{ workspace.name }}</option>
                          }
                        </select>
                      </div>
                      <div>
                        <label class="msa-label" for="settings-landing-page">Default landing page</label>
                        <select
                          id="settings-landing-page"
                          formControlName="landing_page"
                          class="msa-input"
                        >
                          <option value="dashboard">Dashboard</option>
                          <option value="workspaces">Workspaces</option>
                          <option value="playground">Playground</option>
                        </select>
                      </div>
                    </div>
                    <div class="flex justify-end">
                      <button type="submit" class="msa-btn-primary" [disabled]="saving()">
                        <msa-icon name="check" [size]="15" />
                        {{ saving() ? 'Saving…' : 'Save preferences' }}
                      </button>
                    </div>
                  </form>
                </section>
              }

              @case ('profile') {
                <div class="space-y-5">
                  <section class="msa-card">
                    <div class="msa-card-header">
                      <div>
                        <h2 class="msa-section-title">Profile</h2>
                        <p class="text-xs text-muted">Your display name and account identity.</p>
                      </div>
                    </div>
                    <form
                      [formGroup]="profileForm"
                      (ngSubmit)="saveProfile()"
                      class="space-y-4 p-5 sm:p-6"
                    >
                      <div>
                        <label class="msa-label" for="settings-display-name">Display name</label>
                        <input
                          id="settings-display-name"
                          formControlName="display_name"
                          type="text"
                          class="msa-input"
                          placeholder="Jane Doe"
                        />
                      </div>
                      <div>
                        <label class="msa-label" for="settings-email">Email</label>
                        <input
                          id="settings-email"
                          type="email"
                          class="msa-input bg-canvas"
                          [value]="auth.user()?.email"
                          readonly
                        />
                        <p class="mt-1 text-[11px] text-slate-400">
                          Email changes are not available in the app; contact your administrator.
                        </p>
                      </div>
                      <div class="flex justify-end">
                        <button type="submit" class="msa-btn-primary" [disabled]="saving()">
                          {{ saving() ? 'Saving…' : 'Save profile' }}
                        </button>
                      </div>
                    </form>
                  </section>

                  <section class="msa-card">
                    <div class="msa-card-header">
                      <div>
                        <h2 class="msa-section-title">Change password</h2>
                        <p class="text-xs text-muted">
                          Changing your password revokes refresh tokens on other devices.
                        </p>
                      </div>
                    </div>
                    <form
                      [formGroup]="passwordForm"
                      (ngSubmit)="changePassword()"
                      class="grid gap-4 p-5 sm:grid-cols-2 sm:p-6"
                    >
                      <div class="sm:col-span-2">
                        <label class="msa-label" for="settings-current-password">Current password</label>
                        <input
                          id="settings-current-password"
                          formControlName="current_password"
                          type="password"
                          autocomplete="current-password"
                          class="msa-input"
                        />
                      </div>
                      <div>
                        <label class="msa-label" for="settings-new-password">New password</label>
                        <input
                          id="settings-new-password"
                          formControlName="new_password"
                          type="password"
                          autocomplete="new-password"
                          class="msa-input"
                        />
                      </div>
                      <div>
                        <label class="msa-label" for="settings-confirm-password">Confirm new password</label>
                        <input
                          id="settings-confirm-password"
                          formControlName="confirm_password"
                          type="password"
                          autocomplete="new-password"
                          class="msa-input"
                        />
                      </div>
                      @if (passwordError()) {
                        <p class="sm:col-span-2 text-xs text-rose-600">{{ passwordError() }}</p>
                      }
                      <div class="flex justify-end sm:col-span-2">
                        <button type="submit" class="msa-btn-primary" [disabled]="saving()">
                          {{ saving() ? 'Updating…' : 'Change password' }}
                        </button>
                      </div>
                    </form>
                  </section>
                </div>
              }

              @case ('workspace') {
                @if (selectedWorkspace(); as workspace) {
                  <div class="space-y-5">
                    <section class="msa-card">
                      <div class="msa-card-header">
                        <div>
                          <h2 class="msa-section-title">Workspace details</h2>
                          <p class="text-xs text-muted">
                            Visible to every member of this workspace.
                          </p>
                        </div>
                        <span class="msa-badge bg-slate-50 text-slate-500">
                          {{ workspace.role }}
                        </span>
                      </div>
                      <form
                        [formGroup]="workspaceForm"
                        (ngSubmit)="saveWorkspace()"
                        class="space-y-4 p-5 sm:p-6"
                      >
                        <div>
                          <label class="msa-label" for="settings-workspace-name">Name</label>
                          <input
                            id="settings-workspace-name"
                            formControlName="name"
                            type="text"
                            class="msa-input"
                            [readonly]="!canManage()"
                          />
                        </div>
                        <div>
                          <label class="msa-label" for="settings-workspace-description">Description</label>
                          <textarea
                            id="settings-workspace-description"
                            formControlName="description"
                            rows="3"
                            class="msa-input resize-y"
                            placeholder="What this workspace is used for"
                            [readonly]="!canManage()"
                          ></textarea>
                        </div>
                        <div class="flex justify-end">
                          @if (canManage()) {
                            <button type="submit" class="msa-btn-primary" [disabled]="saving()">
                              {{ saving() ? 'Saving…' : 'Save workspace' }}
                            </button>
                          } @else {
                            <p class="text-xs text-muted">Viewers cannot edit workspace details.</p>
                          }
                        </div>
                      </form>
                    </section>

                    <section class="msa-card">
                      <div class="msa-card-header">
                        <h2 class="msa-section-title">Projects</h2>
                        <span class="msa-badge bg-slate-50 text-slate-500">{{ projects().length }}</span>
                      </div>
                      @if (projects().length) {
                        <ul class="divide-y divide-line">
                          @for (project of projects(); track project.id) {
                            <li class="flex flex-wrap items-center gap-3 px-5 py-3">
                              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand">
                                <msa-icon name="folder" [size]="15" />
                              </span>
                              <span class="min-w-0 flex-1">
                                <span class="block truncate text-sm font-medium text-ink">{{ project.name }}</span>
                                <span class="block truncate text-[11px] text-slate-400">
                                  {{ project.description || 'No description' }}
                                </span>
                              </span>
                              <span class="text-[11px] text-slate-400">Created {{ project.created_at | msaDate: 'mediumDate' }}</span>
                            </li>
                          }
                        </ul>
                      } @else {
                        <p class="px-5 py-8 text-sm text-muted">No projects in this workspace yet.</p>
                      }
                    </section>
                  </div>
                }
              }

              @case ('team') {
                <div class="space-y-5">
                  <section class="msa-card">
                    <div class="msa-card-header">
                      <div>
                        <h2 class="msa-section-title">Team members</h2>
                        <p class="text-xs text-muted">
                          Workspace roles control who can read, edit and administer resources.
                        </p>
                      </div>
                      <span class="msa-badge bg-slate-50 text-slate-500">{{ members().length }}</span>
                    </div>

                    @if (canManage()) {
                      <form
                        [formGroup]="memberForm"
                        (ngSubmit)="inviteMember()"
                        class="grid gap-3 border-b border-line bg-canvas/40 p-5 sm:grid-cols-[1.5fr_0.8fr_auto]"
                      >
                        <div>
                          <label class="msa-label" for="settings-member-email">Invite by email</label>
                          <input
                            id="settings-member-email"
                            formControlName="email"
                            type="email"
                            class="msa-input"
                            placeholder="teammate@example.com"
                          />
                        </div>
                        <div>
                          <label class="msa-label" for="settings-member-role">Role</label>
                          <select id="settings-member-role" formControlName="role" class="msa-input">
                            @for (role of assignableRoles(); track role) {
                              <option [value]="role">{{ role }}</option>
                            }
                          </select>
                        </div>
                        <div class="flex items-end">
                          <button type="submit" class="msa-btn-primary" [disabled]="saving()">
                            <msa-icon name="plus" [size]="15" /> Add member
                          </button>
                        </div>
                      </form>
                    }

                    @if (members().length) {
                      <ul class="divide-y divide-line">
                        @for (member of members(); track member.id) {
                          <li class="flex flex-wrap items-center gap-3 px-5 py-3">
                            <span class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-[11px] font-semibold text-white">
                              {{ initials(member.user.display_name || member.user.email) }}
                            </span>
                            <span class="min-w-0 flex-1">
                              <span class="block truncate text-sm font-medium text-ink">
                                {{ member.user.display_name || member.user.email }}
                              </span>
                              <span class="block truncate text-[11px] text-slate-400">{{ member.user.email }}</span>
                            </span>
                            @if (canEditMember(member)) {
                              <select
                                [value]="member.role"
                                (change)="changeRole(member, $any($event.target).value)"
                                class="rounded-lg border border-line bg-white px-2 py-1 text-xs"
                                [attr.aria-label]="'Role for ' + member.user.email"
                              >
                                @for (role of assignableRoles(); track role) {
                                  <option [value]="role" [selected]="role === member.role">{{ role }}</option>
                                }
                              </select>
                              <button
                                type="button"
                                class="msa-btn-ghost text-rose-600 hover:bg-rose-50"
                                (click)="removeMember(member)"
                              >
                                Remove
                              </button>
                            } @else {
                              <span class="msa-badge bg-slate-50 text-slate-500">{{ member.role }}</span>
                            }
                          </li>
                        }
                      </ul>
                    } @else {
                      <p class="px-5 py-8 text-sm text-muted">No members yet.</p>
                    }
                  </section>

                  <section class="msa-card p-5">
                    <h2 class="msa-section-title">Role permissions</h2>
                    <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      @for (permission of permissions; track permission.role) {
                        <div class="rounded-xl border border-line p-3">
                          <p class="text-xs font-semibold uppercase tracking-wide text-brand">{{ permission.role }}</p>
                          <p class="mt-1 text-[11px] leading-relaxed text-slate-500">{{ permission.detail }}</p>
                        </div>
                      }
                    </div>
                  </section>
                </div>
              }

              @case ('providers') {
                <section class="msa-card">
                  <div class="msa-card-header">
                    <div>
                      <h2 class="msa-section-title">AI providers and models</h2>
                      <p class="text-xs text-muted">
                        Credentials are encrypted at rest and never shown after saving.
                      </p>
                    </div>
                    @if (projects().length) {
                      <label class="flex items-center gap-2 text-xs text-muted">
                        <span class="font-medium">Project</span>
                        <select
                          class="msa-input min-w-[180px]"
                          [value]="settingsProjectId()"
                          (change)="selectProject($any($event.target).value)"
                          aria-label="Provider project"
                        >
                          @for (project of projects(); track project.id) {
                            <option [value]="project.id">{{ project.name }}</option>
                          }
                        </select>
                      </label>
                    }
                  </div>
                  <div class="p-5">
                    @if (settingsProjectId()) {
                      <msa-provider-manager
                        [projectId]="settingsProjectId()"
                        [canManage]="canManage()"
                      />
                    } @else {
                      <p class="text-sm text-muted">Create a project before adding a provider.</p>
                    }
                  </div>
                </section>
              }

              @case ('security') {
                <div class="space-y-5">
                  <section class="msa-card">
                    <div class="msa-card-header">
                      <div>
                        <h2 class="msa-section-title">Account security</h2>
                        <p class="text-xs text-muted">Passwords, sessions and sign-out.</p>
                      </div>
                    </div>
                    <div class="space-y-4 p-5 sm:p-6">
                      <div class="rounded-xl border border-line bg-canvas/40 p-4">
                        <p class="text-xs font-semibold text-ink">Current session</p>
                        <p class="mt-1 text-xs text-slate-500">
                          {{ auth.user()?.email }} · access tokens expire after 15 minutes and refresh tokens rotate.
                        </p>
                        <button type="button" class="msa-btn-secondary mt-3" (click)="auth.logout()">
                          <msa-icon name="logout" [size]="15" /> Sign out
                        </button>
                      </div>
                      <div class="rounded-xl border border-line p-4">
                        <p class="text-xs font-semibold text-ink">Password</p>
                        <p class="mt-1 text-xs text-slate-500">
                          Use the password form on the Profile & account page. A change revokes refresh tokens on other devices.
                        </p>
                        <button type="button" class="msa-btn-secondary mt-3" (click)="selectSection('profile')">
                          Change password
                        </button>
                      </div>
                      <div class="rounded-xl border border-line p-4">
                        <p class="text-xs font-semibold text-ink">Data retention</p>
                        <p class="mt-1 text-xs text-slate-500">
                          @if (about()?.features?.observability_retention_days) {
                            Raw traces are retained for {{ about()!.features.observability_retention_days }} days. Rollups are retained.
                          } @else {
                            Raw traces are retained indefinitely. Evaluation, dataset and audit records remain until deleted.
                          }
                        </p>
                      </div>
                      @if (canManage()) {
                        <div class="rounded-xl border border-line p-4">
                          <p class="text-xs font-semibold text-ink">Export workspace data</p>
                          <p class="mt-1 text-xs text-slate-500">
                            Download a JSON snapshot of workspace content. Provider credentials,
                            password hashes and session tokens are never included.
                          </p>
                          <button type="button" class="msa-btn-secondary mt-3" (click)="exportWorkspace()">
                            <msa-icon name="download" [size]="15" /> Export JSON
                          </button>
                        </div>
                      }
                    </div>
                  </section>

                  @if (canDeleteWorkspace()) {
                    <section class="msa-card border-rose-200">
                      <div class="msa-card-header border-rose-100">
                        <div>
                          <h2 class="msa-section-title text-rose-700">Danger zone</h2>
                          <p class="text-xs text-muted">
                            Deleting a workspace removes its projects, datasets, runs, traces and audit history.
                          </p>
                        </div>
                      </div>
                      <div class="flex flex-wrap items-center justify-between gap-3 p-5">
                        <p class="text-xs text-slate-500">
                          This action cannot be undone. Export any reports first.
                        </p>
                        <button type="button" class="msa-btn-secondary border-rose-200 text-rose-700 hover:bg-rose-50" (click)="deleteWorkspace()">
                          <msa-icon name="trash" [size]="15" /> Delete workspace
                        </button>
                      </div>
                    </section>
                  }
                </div>
              }

              @case ('audit') {
                <div class="space-y-5">
                  <section class="msa-card">
                    <div class="msa-card-header">
                      <div>
                        <h2 class="msa-section-title">Workspace activity</h2>
                        <p class="text-xs text-muted">
                          Sign-ins, configuration changes, membership changes and provider updates.
                        </p>
                      </div>
                      <span class="msa-badge bg-slate-50 text-slate-500">{{ workspaceAudit().length }}</span>
                    </div>
                    @if (canManage()) {
                      @if (workspaceAudit().length) {
                        <div class="overflow-x-auto">
                          <table class="msa-table">
                            <thead>
                              <tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th></tr>
                            </thead>
                            <tbody>
                              @for (event of workspaceAudit(); track event.id) {
                                <tr>
                                  <td class="text-xs text-slate-500">{{ event.created_at | msaDate: 'short' }}</td>
                                  <td class="text-xs">{{ event.actor_email || 'System' }}</td>
                                  <td class="text-xs font-medium text-ink">{{ event.action }}</td>
                                  <td class="text-[11px] text-slate-400">{{ event.target_type || '—' }}</td>
                                </tr>
                              }
                            </tbody>
                          </table>
                        </div>
                      } @else {
                        <p class="px-5 py-8 text-sm text-muted">No workspace activity recorded yet.</p>
                      }
                    } @else {
                      <p class="px-5 py-8 text-sm text-muted">
                        Workspace audit history is available to admins and the owner.
                      </p>
                    }
                  </section>

                  <section class="msa-card">
                    <div class="msa-card-header">
                      <h2 class="msa-section-title">Account activity</h2>
                      <span class="msa-badge bg-slate-50 text-slate-500">{{ accountAudit().length }}</span>
                    </div>
                    @if (accountAudit().length) {
                      <div class="overflow-x-auto">
                        <table class="msa-table">
                          <thead><tr><th>When</th><th>Action</th><th>Details</th></tr></thead>
                          <tbody>
                            @for (event of accountAudit(); track event.id) {
                              <tr>
                                <td class="text-xs text-slate-500">{{ event.created_at | msaDate: 'short' }}</td>
                                <td class="text-xs font-medium text-ink">{{ event.action }}</td>
                                <td class="text-[11px] text-slate-400">{{ event.metadata | json }}</td>
                              </tr>
                            }
                          </tbody>
                        </table>
                      </div>
                    } @else {
                      <p class="px-5 py-8 text-sm text-muted">No account activity recorded yet.</p>
                    }
                  </section>
                </div>
              }

              @case ('about') {
                @if (about(); as info) {
                  <div class="space-y-5">
                    <section class="msa-card overflow-hidden">
                      <div class="border-b border-line bg-gradient-to-r from-navy to-[#243b5a] p-6 text-white">
                        <div class="flex items-center gap-3">
                          <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 text-lg font-bold">M</span>
                          <div>
                            <p class="text-lg font-semibold">{{ info.name }}</p>
                            <p class="text-xs text-slate-300">Version {{ info.version }} · API {{ info.api_version }}</p>
                          </div>
                        </div>
                      </div>
                      <dl class="grid gap-4 p-5 sm:grid-cols-2 sm:p-6">
                        <div><dt class="text-[10px] uppercase tracking-wide text-slate-400">Environment</dt><dd class="mt-1 text-sm text-ink">{{ info.environment }}</dd></div>
                        <div><dt class="text-[10px] uppercase tracking-wide text-slate-400">Database</dt><dd class="mt-1 text-sm text-ink">{{ info.database }}</dd></div>
                        <div><dt class="text-[10px] uppercase tracking-wide text-slate-400">Server time</dt><dd class="mt-1 text-sm text-ink">{{ info.server_time | msaDate: 'medium' }}</dd></div>
                        <div><dt class="text-[10px] uppercase tracking-wide text-slate-400">Trace retention</dt><dd class="mt-1 text-sm text-ink">{{ info.features.observability_retention_days ? info.features.observability_retention_days + ' days' : 'Indefinite' }}</dd></div>
                      </dl>
                    </section>
                    <section class="msa-card p-5 sm:p-6">
                      <h2 class="msa-section-title">Documentation and support</h2>
                      <div class="mt-3 grid gap-2 sm:grid-cols-2">
                        <a class="msa-btn-secondary justify-start" [href]="info.links.api_docs" target="_blank" rel="noopener">API documentation</a>
                        <a class="msa-btn-secondary justify-start" [href]="info.links.openapi" target="_blank" rel="noopener">OpenAPI schema</a>
                        @if (info.links.documentation) {
                          <a class="msa-btn-secondary justify-start" [href]="info.links.documentation" target="_blank" rel="noopener">Product documentation</a>
                        }
                        @if (info.links.support) {
                          <a class="msa-btn-secondary justify-start" [href]="info.links.support" target="_blank" rel="noopener">Support</a>
                        }
                      </div>
                    </section>
                  </div>
                } @else {
                  <p class="msa-card p-6 text-sm text-muted">Build information is unavailable.</p>
                }
              }
            }
          }
        </div>
      </div>
    </div>
  `,
})
export class SettingsComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly settingsService = inject(SettingsService);
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly sections = SECTIONS;
  readonly active = signal<SettingsSection>('general');
  readonly workspaces = signal<Workspace[]>([]);
  readonly members = signal<Membership[]>([]);
  readonly projects = signal<Project[]>([]);
  readonly workspaceAudit = signal<AuditEventRow[]>([]);
  readonly accountAudit = signal<AuditEventRow[]>([]);
  readonly about = signal<AboutInfo | null>(null);
  readonly selectedWorkspaceId = signal<string>('');
  readonly settingsProjectId = signal<string>('');
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly notice = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly passwordError = signal<string | null>(null);

  readonly selectedWorkspace = computed(
    () =>
      this.workspaces().find(
        (workspace) => workspace.id === this.selectedWorkspaceId(),
      ) ?? null,
  );

  readonly canManage = computed(() => {
    const role = this.selectedWorkspace()?.role;
    return role === 'owner' || role === 'admin';
  });
  readonly canDeleteWorkspace = computed(
    () => this.selectedWorkspace()?.role === 'owner',
  );
  readonly assignableRoles = computed<WorkspaceRole[]>(() =>
    this.selectedWorkspace()?.role === 'owner'
      ? ['admin', 'member', 'viewer']
      : ['member', 'viewer'],
  );

  readonly permissions = [
    { role: 'Owner', detail: 'Full control, including deleting the workspace and managing admins.' },
    { role: 'Admin', detail: 'Manage projects, providers, members and workspace settings.' },
    { role: 'Member', detail: 'Create and run evaluations; manage own projects and datasets.' },
    { role: 'Viewer', detail: 'Read-only access to workspace resources and results.' },
  ];

  readonly generalForm = this.fb.nonNullable.group({
    timezone: ['UTC'],
    date_format: this.fb.nonNullable.control<UserPreferences['date_format']>('medium'),
    default_workspace: [''],
    landing_page: this.fb.nonNullable.control<UserPreferences['landing_page']>('dashboard'),
  });

  readonly profileForm = this.fb.nonNullable.group({
    display_name: [''],
  });

  readonly passwordForm = this.fb.nonNullable.group({
    current_password: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', Validators.required],
  });

  readonly workspaceForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    description: [''],
  });

  readonly memberForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: this.fb.nonNullable.control<WorkspaceRole>('member'),
  });

  readonly timezones = this.supportedTimezones();

  ngOnInit(): void {
    const requested = this.route.snapshot.queryParamMap.get('section');
    if (SECTIONS.some((section) => section.key === requested)) {
      this.active.set(requested as SettingsSection);
    }
    this.hydrateForms();
    this.load();
  }

  selectWorkspace(workspaceId: string): void {
    const workspace = this.workspaces().find((row) => row.id === workspaceId);
    if (!workspace) {
      return;
    }
    this.selectedWorkspaceId.set(workspaceId);
    this.hydrateWorkspace(workspace);
    this.clearMessages();
    this.loading.set(true);
    this.loadWorkspaceData(workspaceId);
  }

  selectSection(section: SettingsSection): void {
    this.active.set(section);
    this.notice.set(null);
    this.error.set(null);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { section },
      replaceUrl: true,
    });
  }

  saveGeneral(): void {
    const value = this.generalForm.getRawValue();
    this.saving.set(true);
    this.clearMessages();
    this.auth
      .updateProfile({
        preferences: {
          timezone: value.timezone.trim() || 'UTC',
          date_format: value.date_format,
          default_workspace: value.default_workspace || null,
          landing_page: value.landing_page,
        },
      })
      .subscribe({
        next: () => this.done('Preferences saved.'),
        error: (error: unknown) => this.fail(error),
      });
  }

  saveProfile(): void {
    const name = this.profileForm.getRawValue().display_name.trim();
    this.saving.set(true);
    this.clearMessages();
    this.auth.updateProfile({ display_name: name }).subscribe({
      next: () => this.done('Profile updated.'),
      error: (error: unknown) => this.fail(error),
    });
  }

  changePassword(): void {
    this.passwordError.set(null);
    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    const value = this.passwordForm.getRawValue();
    if (value.new_password !== value.confirm_password) {
      this.passwordError.set('The new passwords do not match.');
      return;
    }
    this.saving.set(true);
    this.clearMessages();
    this.auth
      .changePassword(value.current_password, value.new_password)
      .subscribe({
        next: (result) => {
          this.passwordForm.reset({
            current_password: '',
            new_password: '',
            confirm_password: '',
          });
          this.done(
            `${result.detail} ${result.refresh_tokens_revoked} refresh token(s) revoked.`,
          );
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.passwordError.set(apiErrorMessage(error));
        },
      });
  }

  saveWorkspace(): void {
    const workspace = this.selectedWorkspace();
    if (!workspace || !this.canManage()) {
      return;
    }
    if (this.workspaceForm.invalid) {
      this.workspaceForm.markAllAsTouched();
      return;
    }
    const value = this.workspaceForm.getRawValue();
    this.saving.set(true);
    this.clearMessages();
    this.workspaceService
      .update(workspace.id, {
        name: value.name.trim(),
        settings: {
          ...workspace.settings,
          description: value.description.trim(),
        },
      })
      .subscribe({
        next: (updated) => {
          this.workspaces.update((rows) =>
            rows.map((row) => (row.id === updated.id ? updated : row)),
          );
          this.done('Workspace updated.');
        },
        error: (error: unknown) => this.fail(error),
      });
  }

  selectProject(projectId: string): void {
    this.settingsProjectId.set(projectId);
  }

  inviteMember(): void {
    const workspace = this.selectedWorkspace();
    if (!workspace || this.memberForm.invalid) {
      this.memberForm.markAllAsTouched();
      return;
    }
    const value = this.memberForm.getRawValue();
    this.saving.set(true);
    this.clearMessages();
    this.workspaceService
      .addMember(workspace.id, value.email.trim(), value.role)
      .subscribe({
        next: () => {
          this.memberForm.reset({ email: '', role: 'member' });
          this.loadWorkspaceData(workspace.id);
          this.done('Member added.');
        },
        error: (error: unknown) => this.fail(error),
      });
  }

  changeRole(member: Membership, role: WorkspaceRole): void {
    const workspace = this.selectedWorkspace();
    if (!workspace || role === member.role) {
      return;
    }
    this.saving.set(true);
    this.clearMessages();
    this.workspaceService
      .updateMemberRole(workspace.id, member.id, role)
      .subscribe({
        next: () => {
          this.loadWorkspaceData(workspace.id);
          this.done('Member role updated.');
        },
        error: (error: unknown) => this.fail(error),
      });
  }

  removeMember(member: Membership): void {
    const workspace = this.selectedWorkspace();
    if (!workspace) {
      return;
    }
    if (!globalThis.confirm(`Remove ${member.user.email} from ${workspace.name}?`)) {
      return;
    }
    this.saving.set(true);
    this.clearMessages();
    this.workspaceService.removeMember(workspace.id, member.id).subscribe({
      next: () => {
        this.loadWorkspaceData(workspace.id);
        this.done('Member removed.');
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  exportWorkspace(): void {
    const workspace = this.selectedWorkspace();
    if (!workspace || !this.canManage()) {
      return;
    }
    this.clearMessages();
    this.workspaceService.exportData(workspace.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `modelscope-workspace-${workspace.id}.json`;
        link.click();
        URL.revokeObjectURL(url);
        this.done('Workspace export downloaded.');
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  deleteWorkspace(): void {
    const workspace = this.selectedWorkspace();
    if (!workspace || !this.canDeleteWorkspace()) {
      return;
    }
    if (
      !globalThis.confirm(
        `Delete "${workspace.name}" and all of its projects, runs and audit history? This cannot be undone.`,
      )
    ) {
      return;
    }
    this.saving.set(true);
    this.clearMessages();
    this.workspaceService.delete(workspace.id).subscribe({
      next: () => {
        this.workspaces.update((rows) =>
          rows.filter((row) => row.id !== workspace.id),
        );
        const next = this.workspaces()[0] ?? null;
        this.selectedWorkspaceId.set(next?.id ?? '');
        this.members.set([]);
        this.projects.set([]);
        this.workspaceAudit.set([]);
        if (next) {
          this.loadWorkspaceData(next.id);
        }
        this.done('Workspace deleted.');
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  canEditMember(member: Membership): boolean {
    const currentRole = this.selectedWorkspace()?.role;
    if (!this.canManage() || member.role === 'owner') {
      return false;
    }
    return currentRole === 'owner' || member.role !== 'admin';
  }

  initials(name: string): string {
    return name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase();
  }

  private load(): void {
    this.loading.set(true);
    forkJoin({
      workspaces: this.workspaceService.list(),
      accountAudit: this.settingsService.accountAudit().pipe(catchError(() => of(null))),
      about: this.settingsService.about().pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ workspaces, accountAudit, about }) => {
        this.workspaces.set(workspaces.results);
        this.accountAudit.set(accountAudit?.results ?? []);
        this.about.set(about);
        const preferred = this.auth.user()?.preferences?.default_workspace;
        const selected =
          workspaces.results.find((row) => row.id === preferred) ??
          workspaces.results[0] ??
          null;
        this.selectedWorkspaceId.set(selected?.id ?? '');
        if (selected) {
          this.hydrateWorkspace(selected);
          this.loadWorkspaceData(selected.id);
        } else {
          this.loading.set(false);
        }
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.fail(error);
      },
    });
  }

  private loadWorkspaceData(workspaceId: string): void {
    forkJoin({
      projects: this.projectService.list(workspaceId),
      members: this.workspaceService.members(workspaceId),
      audit: this.workspaceService.audit(workspaceId).pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ projects, members, audit }) => {
        this.projects.set(projects.results);
        this.members.set(members.results);
        this.workspaceAudit.set(audit?.results ?? []);
        this.settingsProjectId.set(
          projects.results[0]?.id ?? this.settingsProjectId(),
        );
        this.loading.set(false);
        this.saving.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.fail(error);
      },
    });
  }

  private hydrateForms(): void {
    const preferences = this.auth.user()?.preferences;
    this.generalForm.reset({
      timezone: preferences?.timezone ?? 'UTC',
      date_format: preferences?.date_format ?? 'medium',
      default_workspace: preferences?.default_workspace ?? '',
      landing_page: preferences?.landing_page ?? 'dashboard',
    });
    this.profileForm.reset({
      display_name: this.auth.user()?.display_name ?? '',
    });
  }

  private hydrateWorkspace(workspace: Workspace): void {
    this.workspaceForm.reset({
      name: workspace.name,
      description: String(workspace.settings?.['description'] ?? ''),
    });
  }

  private done(message: string): void {
    this.saving.set(false);
    this.error.set(null);
    this.notice.set(message);
  }

  private fail(error: unknown): void {
    this.saving.set(false);
    this.notice.set(null);
    this.error.set(apiErrorMessage(error));
  }

  private clearMessages(): void {
    this.notice.set(null);
    this.error.set(null);
  }

  private supportedTimezones(): string[] {
    const intl = Intl as unknown as {
      supportedValuesOf?: (key: string) => string[];
    };
    try {
      return intl.supportedValuesOf?.('timeZone') ?? DEFAULT_TIMEZONES;
    } catch {
      return DEFAULT_TIMEZONES;
    }
  }
}
