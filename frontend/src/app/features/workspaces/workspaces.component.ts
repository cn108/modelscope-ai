import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import {
  Membership,
  Project,
  Workspace,
  WorkspaceRole,
} from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import {
  ProviderConfig,
  ProviderService,
} from '../providers/provider.service';
import { ProviderManagerComponent } from '../providers/provider-manager.component';
import { WorkspaceService } from './workspace.service';

interface WorkspaceCount {
  projects: number;
  members: number;
}

const WORKSPACE_TONES = [
  'from-brand to-sky-500',
  'from-violet to-fuchsia-500',
  'from-emerald-500 to-teal-500',
  'from-amber-500 to-orange-500',
];

@Component({
  selector: 'msa-workspaces',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    DatePipe,
    IconComponent,
    ProviderManagerComponent,
  ],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Workspaces</h1>
          <p class="msa-sub">
            Organise your projects and collaborate with your team.
          </p>
        </div>
        <button
          type="button"
          class="msa-btn-primary"
          (click)="newWorkspaceOpen.set(!newWorkspaceOpen())"
        >
          <msa-icon [name]="newWorkspaceOpen() ? 'close' : 'plus'" [size]="15" />
          {{ newWorkspaceOpen() ? 'Cancel' : 'New workspace' }}
        </button>
      </header>

      @if (error()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
          role="alert"
        >
          <msa-icon name="alert" [size]="16" />
          <span>{{ error() }}</span>
        </p>
      }

      @if (newWorkspaceOpen()) {
        <form
          [formGroup]="workspaceForm"
          (ngSubmit)="createWorkspace()"
          class="msa-card mt-5 flex flex-wrap items-end gap-3 p-4"
        >
          <div class="min-w-[220px] flex-1">
            <label class="msa-label" for="workspace-name">Workspace name</label>
            <input
              id="workspace-name"
              formControlName="name"
              type="text"
              placeholder="Acme Corp"
              class="msa-input"
            />
          </div>
          <button type="submit" [disabled]="busy()" class="msa-btn-primary">
            <msa-icon name="plus" [size]="15" /> Create workspace
          </button>
        </form>
      }

      <div class="mt-5 flex flex-wrap items-center gap-3">
        <div class="relative w-full max-w-xs">
          <span
            class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          >
            <msa-icon name="search" [size]="15" />
          </span>
          <input
            [value]="search()"
            (input)="search.set($any($event.target).value)"
            type="search"
            placeholder="Search workspaces…"
            aria-label="Search workspaces"
            class="msa-input pl-9"
          />
        </div>
        <span class="text-xs text-muted">
          {{ filtered().length }} of {{ workspaces().length }} workspaces
        </span>
      </div>

      @if (loading()) {
        <div class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          @for (placeholder of [1, 2, 3]; track placeholder) {
            <div class="msa-card p-5">
              <div class="msa-skeleton h-10 w-10"></div>
              <div class="msa-skeleton mt-4 h-3 w-32"></div>
              <div class="msa-skeleton mt-2 h-3 w-24"></div>
            </div>
          }
        </div>
      } @else if (workspaces().length) {
        <div class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          @for (workspace of filtered(); track workspace.id) {
            <article
              tabindex="0"
              role="button"
              [attr.aria-pressed]="workspace.id === selected()?.id"
              [class]="
                'msa-card cursor-pointer p-5 transition hover:-translate-y-0.5 hover:shadow-pop ' +
                (workspace.id === selected()?.id
                  ? 'ring-2 ring-brand/40'
                  : '')
              "
              (click)="selectWorkspace(workspace)"
              (keydown.enter)="selectWorkspace(workspace)"
            >
              <div class="flex items-start gap-3">
                <span
                  class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br text-sm font-semibold text-white"
                  [class]="toneFor(workspace)"
                >
                  {{ initialsFor(workspace.name) }}
                </span>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-semibold text-ink">
                    {{ workspace.name }}
                  </p>
                  <p class="text-[11px] text-slate-400">
                    {{ countFor(workspace).projects }} project{{
                      countFor(workspace).projects === 1 ? '' : 's'
                    }}
                    · {{ countFor(workspace).members }} member{{
                      countFor(workspace).members === 1 ? '' : 's'
                    }}
                  </p>
                </div>
                @if (workspace.id === selected()?.id) {
                  <span class="msa-badge bg-emerald-50 text-emerald-700">
                    <span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                    Active
                  </span>
                }
              </div>

              <div class="mt-4 flex items-center justify-between">
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ workspace.role }}
                </span>
                <span class="inline-flex items-center gap-1 text-xs font-medium text-brand">
                  Open <msa-icon name="arrow-right" [size]="13" />
                </span>
              </div>
            </article>
          } @empty {
            <div class="msa-card col-span-full p-10 text-center">
              <p class="text-sm font-medium text-ink">No matching workspaces</p>
              <p class="mt-1 text-xs text-muted">
                Try a different search term.
              </p>
              <button
                type="button"
                class="msa-btn-secondary mt-4"
                (click)="search.set('')"
              >
                Clear search
              </button>
            </div>
          }
        </div>
      } @else {
        <div class="msa-card mt-5 flex flex-col items-center p-12 text-center">
          <span
            class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand"
          >
            <msa-icon name="layers" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">No data yet</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            Create your first workspace to group projects, invite teammates and
            connect providers.
          </p>
          <button
            type="button"
            class="msa-btn-primary mt-5"
            (click)="newWorkspaceOpen.set(true)"
          >
            <msa-icon name="plus" [size]="15" /> Create workspace
          </button>
        </div>
      }

      @if (selected(); as workspace) {
        <section class="mt-8">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 class="text-lg font-semibold tracking-tight text-ink">
                {{ workspace.name }}
              </h2>
              <p class="text-xs text-muted">
                {{ countFor(workspace).projects }} project{{
                  countFor(workspace).projects === 1 ? '' : 's'
                }}
                · {{ countFor(workspace).members }} member{{
                  countFor(workspace).members === 1 ? '' : 's'
                }}
                · your role: {{ workspace.role }}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              @if (canCreateProject) {
                <button
                  type="button"
                  class="msa-btn-secondary"
                  (click)="newProjectOpen.set(!newProjectOpen())"
                >
                  <msa-icon
                    [name]="newProjectOpen() ? 'close' : 'plus'"
                    [size]="15"
                  />
                  {{ newProjectOpen() ? 'Cancel' : 'New project' }}
                </button>
              }
              @if (canManage) {
                <button
                  type="button"
                  class="msa-btn-secondary"
                  (click)="newMemberOpen.set(!newMemberOpen())"
                >
                  <msa-icon name="users" [size]="15" /> Invite member
                </button>
              }
            </div>
          </div>

          @if (newProjectOpen()) {
            <form
              [formGroup]="projectForm"
              (ngSubmit)="createProject()"
              class="msa-card mt-4 grid gap-3 p-4 sm:grid-cols-[1fr_1.4fr_auto]"
            >
              <div>
                <label class="msa-label" for="project-name">Project name</label>
                <input
                  id="project-name"
                  formControlName="name"
                  type="text"
                  placeholder="Customer Support AI"
                  class="msa-input"
                />
              </div>
              <div>
                <label class="msa-label" for="project-description">
                  Description
                </label>
                <input
                  id="project-description"
                  formControlName="description"
                  type="text"
                  placeholder="Optional"
                  class="msa-input"
                />
              </div>
              <div class="flex items-end">
                <button type="submit" [disabled]="busy()" class="msa-btn-primary">
                  <msa-icon name="plus" [size]="15" /> Add project
                </button>
              </div>
            </form>
          }

          @if (newMemberOpen() && canManage) {
            <form
              [formGroup]="memberForm"
              (ngSubmit)="addMember()"
              class="msa-card mt-4 grid gap-3 p-4 sm:grid-cols-[1.4fr_0.8fr_auto]"
            >
              <div>
                <label class="msa-label" for="member-email">Member email</label>
                <input
                  id="member-email"
                  formControlName="email"
                  type="email"
                  placeholder="teammate@example.com"
                  class="msa-input"
                />
              </div>
              <div>
                <label class="msa-label" for="member-role">Role</label>
                <select id="member-role" formControlName="role" class="msa-input">
                  @for (role of assignableRoles; track role) {
                    <option [value]="role">{{ role }}</option>
                  }
                </select>
              </div>
              <div class="flex items-end">
                <button type="submit" [disabled]="busy()" class="msa-btn-primary">
                  <msa-icon name="plus" [size]="15" /> Add member
                </button>
              </div>
            </form>
          }

          <div class="mt-4 grid gap-4 xl:grid-cols-[1.6fr_1fr]">
            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h3 class="msa-section-title">Projects</h3>
                  <p class="text-xs text-muted">
                    Manage projects and their AI providers
                  </p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ projects().length }}
                </span>
              </div>

              @if (busy() && !projects().length) {
                <div class="space-y-2 p-4">
                  @for (placeholder of [1, 2, 3]; track placeholder) {
                    <div class="msa-skeleton h-10 w-full"></div>
                  }
                </div>
              } @else if (projects().length) {
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[620px]">
                    <thead class="bg-canvas/70">
                      <tr>
                        <th class="msa-th">Name</th>
                        <th class="msa-th">Description</th>
                        <th class="msa-th">Providers</th>
                        <th class="msa-th">Created</th>
                        <th class="msa-th text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (project of projects(); track project.id) {
                        <tr class="msa-row hover:bg-canvas/40">
                          <td class="msa-td">
                            <span class="font-medium text-ink">{{
                              project.name
                            }}</span>
                          </td>
                          <td class="msa-td text-slate-500">
                            {{ project.description || '—' }}
                          </td>
                          <td class="msa-td">
                            @if (providersFor(project.id).length) {
                              <span
                                class="inline-flex items-center gap-1.5 text-xs text-slate-600"
                              >
                                <span
                                  class="h-1.5 w-1.5 rounded-full"
                                  [class]="
                                    hasConnected(project.id)
                                      ? 'bg-emerald-500'
                                      : 'bg-slate-300'
                                  "
                                ></span>
                                {{ providersFor(project.id).length }} provider{{
                                  providersFor(project.id).length === 1 ? '' : 's'
                                }}
                              </span>
                            } @else {
                              <span class="text-xs text-slate-400">None</span>
                            }
                          </td>
                          <td class="msa-td text-xs text-slate-400">
                            {{ project.created_at | date: 'mediumDate' }}
                          </td>
                          <td class="msa-td text-right">
                            <button
                              type="button"
                              class="msa-btn-ghost"
                              (click)="toggleProviders(project)"
                            >
                              {{
                                activeProjectId() === project.id
                                  ? 'Hide'
                                  : 'Providers'
                              }}
                              <msa-icon
                                [name]="
                                  activeProjectId() === project.id
                                    ? 'close'
                                    : 'arrow-right'
                                "
                                [size]="13"
                              />
                            </button>
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <div class="flex flex-col items-center px-6 py-10 text-center">
                  <span
                    class="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-50 text-slate-400"
                  >
                    <msa-icon name="folder" [size]="20" />
                  </span>
                  <p class="mt-3 text-sm font-medium text-ink">No projects yet</p>
                  <p class="mt-1 text-xs text-muted">
                    Projects group your datasets, providers and evaluations.
                  </p>
                  @if (canCreateProject) {
                    <button
                      type="button"
                      class="msa-btn-primary mt-4"
                      (click)="newProjectOpen.set(true)"
                    >
                      <msa-icon name="plus" [size]="15" /> Create project
                    </button>
                  }
                </div>
              }

              @if (activeProject(); as project) {
                <div class="border-t border-line bg-canvas/40 p-5">
                  <p class="mb-3 text-xs text-muted">
                    Providers for
                    <span class="font-medium text-ink">{{ project.name }}</span>
                  </p>
                  <msa-provider-manager
                    [projectId]="project.id"
                    [canManage]="canManage"
                    (changed)="updateProviderSummary(project.id, $event)"
                  />
                </div>
              }
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <div>
                  <h3 class="msa-section-title">Members</h3>
                  <p class="text-xs text-muted">Roles and access</p>
                </div>
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ members().length }}
                </span>
              </div>

              @if (members().length) {
                <ul class="divide-y divide-line">
                  @for (member of members(); track member.id) {
                    <li class="flex flex-wrap items-center gap-3 px-5 py-3">
                      <span
                        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand/80 to-violet/80 text-[11px] font-semibold text-white"
                      >
                        {{ initialsFor(member.user.display_name || member.user.email) }}
                      </span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium text-ink">
                          {{ member.user.display_name || member.user.email }}
                        </span>
                        <span class="block truncate text-[11px] text-slate-400">
                          {{ member.user.email }}
                        </span>
                      </span>

                      @if (canEditMember(member)) {
                        <select
                          [value]="member.role"
                          (change)="changeRole(member, $event)"
                          class="rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink"
                          [attr.aria-label]="'Role for ' + member.user.email"
                        >
                          @for (role of assignableRoles; track role) {
                            <option [value]="role" [selected]="role === member.role">
                              {{ role }}
                            </option>
                          }
                        </select>
                        <button
                          type="button"
                          class="msa-btn-ghost text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          [disabled]="busy()"
                          (click)="removeMember(member)"
                        >
                          <msa-icon name="trash" [size]="13" /> Remove
                        </button>
                      } @else {
                        <span class="msa-badge bg-slate-50 text-slate-500">
                          {{ member.role }}
                        </span>
                      }
                    </li>
                  }
                </ul>
              } @else {
                <p class="px-5 py-8 text-center text-sm text-muted">
                  No members yet.
                </p>
              }
            </section>
          </div>
        </section>
      }
    </div>
  `,
})
export class WorkspacesComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly providerService = inject(ProviderService);
  private readonly fb = inject(FormBuilder);

  readonly workspaces = signal<Workspace[]>([]);
  readonly counts = signal<Record<string, WorkspaceCount>>({});
  readonly selected = signal<Workspace | null>(null);
  readonly projects = signal<Project[]>([]);
  readonly members = signal<Membership[]>([]);
  readonly providersByProject = signal<Record<string, ProviderConfig[]>>({});
  readonly activeProjectId = signal<string | null>(null);
  readonly search = signal('');
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly newWorkspaceOpen = signal(false);
  readonly newProjectOpen = signal(false);
  readonly newMemberOpen = signal(false);

  readonly filtered = computed(() => {
    const term = this.search().trim().toLowerCase();
    const workspaces = this.workspaces();
    return term
      ? workspaces.filter((workspace) =>
          workspace.name.toLowerCase().includes(term),
        )
      : workspaces;
  });

  readonly activeProject = computed(
    () =>
      this.projects().find(
        (project) => project.id === this.activeProjectId(),
      ) ?? null,
  );

  readonly workspaceForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
  });
  readonly projectForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    description: [''],
  });
  readonly memberForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: this.fb.nonNullable.control<WorkspaceRole>('member'),
  });

  get canManage(): boolean {
    const role = this.selected()?.role;
    return role === 'owner' || role === 'admin';
  }

  get canManageAdmins(): boolean {
    return this.selected()?.role === 'owner';
  }

  get canCreateProject(): boolean {
    const workspace = this.selected();
    return workspace !== null && workspace.role !== 'viewer';
  }

  get assignableRoles(): WorkspaceRole[] {
    return this.canManageAdmins
      ? ['admin', 'member', 'viewer']
      : ['member', 'viewer'];
  }

  ngOnInit(): void {
    this.loadWorkspaces();
  }

  toneFor(workspace: Workspace): string {
    let hash = 0;
    for (const char of workspace.name) {
      hash = (hash + char.charCodeAt(0)) % WORKSPACE_TONES.length;
    }
    return WORKSPACE_TONES[hash];
  }

  initialsFor(name: string): string {
    return name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase();
  }

  countFor(workspace: Workspace): WorkspaceCount {
    return this.counts()[workspace.id] ?? { projects: 0, members: 0 };
  }

  providersFor(projectId: string): ProviderConfig[] {
    return this.providersByProject()[projectId] ?? [];
  }

  hasConnected(projectId: string): boolean {
    return this.providersFor(projectId).some(
      (provider) => provider.connection_status === 'connected',
    );
  }

  selectWorkspace(workspace: Workspace): void {
    this.selected.set(workspace);
    this.error.set(null);
    this.activeProjectId.set(null);
    this.newProjectOpen.set(false);
    this.newMemberOpen.set(false);
    this.loadWorkspaceData(workspace.id);
  }

  toggleProviders(project: Project): void {
    const isOpen = this.activeProjectId() === project.id;
    this.activeProjectId.set(isOpen ? null : project.id);
  }

  updateProviderSummary(projectId: string, providers: ProviderConfig[]): void {
    this.providersByProject.update((current) => ({
      ...current,
      [projectId]: providers,
    }));
  }

  createWorkspace(): void {
    if (this.workspaceForm.invalid) {
      this.workspaceForm.markAllAsTouched();
      return;
    }
    const name = this.workspaceForm.getRawValue().name.trim();
    if (!name) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.workspaceService.create(name).subscribe({
      next: (workspace) => {
        this.workspaceForm.reset({ name: '' });
        this.newWorkspaceOpen.set(false);
        this.busy.set(false);
        this.loadWorkspaces(workspace.id);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  createProject(): void {
    const workspace = this.selected();
    if (!workspace) {
      return;
    }
    if (this.projectForm.invalid) {
      this.projectForm.markAllAsTouched();
      return;
    }
    const { name, description } = this.projectForm.getRawValue();
    if (!name.trim()) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.projectService
      .create(workspace.id, name.trim(), description.trim())
      .subscribe({
        next: () => {
          this.projectForm.reset({ name: '', description: '' });
          this.newProjectOpen.set(false);
          this.busy.set(false);
          this.loadWorkspaceData(workspace.id);
        },
        error: (error: unknown) => {
          this.busy.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  addMember(): void {
    const workspace = this.selected();
    if (!workspace) {
      return;
    }
    if (this.memberForm.invalid) {
      this.memberForm.markAllAsTouched();
      return;
    }
    const { email, role } = this.memberForm.getRawValue();
    this.busy.set(true);
    this.error.set(null);
    this.workspaceService.addMember(workspace.id, email.trim(), role).subscribe({
      next: () => {
        this.memberForm.reset({ email: '', role: 'member' });
        this.newMemberOpen.set(false);
        this.busy.set(false);
        this.loadWorkspaceData(workspace.id);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  changeRole(membership: Membership, event: Event): void {
    const workspace = this.selected();
    if (!workspace) {
      return;
    }
    const role = (event.target as HTMLSelectElement).value as WorkspaceRole;
    if (role === membership.role) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.workspaceService
      .updateMemberRole(workspace.id, membership.id, role)
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.loadWorkspaceData(workspace.id);
        },
        error: (error: unknown) => {
          this.busy.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  removeMember(membership: Membership): void {
    const workspace = this.selected();
    if (!workspace) {
      return;
    }
    if (
      !globalThis.confirm(
        `Remove ${membership.user.email} from ${workspace.name}?`,
      )
    ) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.workspaceService
      .removeMember(workspace.id, membership.id)
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.loadWorkspaceData(workspace.id);
        },
        error: (error: unknown) => {
          this.busy.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  canEditMember(membership: Membership): boolean {
    return (
      this.canManage &&
      membership.role !== 'owner' &&
      (this.canManageAdmins || membership.role !== 'admin')
    );
  }

  private loadWorkspaces(selectId?: string): void {
    this.loading.set(true);
    this.workspaceService.list().subscribe({
      next: (page) => {
        this.workspaces.set(page.results);
        const targetId =
          selectId ?? this.selected()?.id ?? page.results[0]?.id ?? null;
        const workspace =
          page.results.find((candidate) => candidate.id === targetId) ??
          page.results[0] ??
          null;
        this.selected.set(workspace);
        this.loading.set(false);
        if (workspace) {
          this.loadWorkspaceData(workspace.id);
        } else {
          this.projects.set([]);
          this.members.set([]);
          this.providersByProject.set({});
        }
        this.loadCounts(
          page.results.filter((candidate) => candidate.id !== workspace?.id),
        );
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadCounts(workspaces: Workspace[]): void {
    if (!workspaces.length) {
      this.counts.set({});
      return;
    }
    forkJoin(
      workspaces.map((workspace) =>
        forkJoin({
          projects: this.projectService
            .list(workspace.id)
            .pipe(catchError(() => of(null))),
          members: this.workspaceService
            .members(workspace.id)
            .pipe(catchError(() => of(null))),
        }).pipe(
          map(
            (result) =>
              [
                workspace.id,
                {
                  projects: result.projects?.count ?? 0,
                  members: result.members?.count ?? 0,
                },
              ] as const,
          ),
        ),
      ),
    ).subscribe({
      next: (entries) => this.counts.set(Object.fromEntries(entries)),
      error: () => undefined,
    });
  }

  private loadWorkspaceData(workspaceId: string): void {
    this.busy.set(true);
    forkJoin({
      projects: this.projectService.list(workspaceId),
      members: this.workspaceService.members(workspaceId),
    }).subscribe({
      next: ({ projects, members }) => {
        this.projects.set(projects.results);
        this.members.set(members.results);
        this.counts.update((current) => ({
          ...current,
          [workspaceId]: { projects: projects.count, members: members.count },
        }));
        this.busy.set(false);
        this.loadProviderSummaries(projects.results);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadProviderSummaries(projects: Project[]): void {
    if (!projects.length) {
      this.providersByProject.set({});
      return;
    }
    forkJoin(
      projects.map((project) =>
        this.providerService
          .list(project.id)
          .pipe(catchError(() => of([] as ProviderConfig[]))),
      ),
    ).subscribe({
      next: (results) => {
        const summaries: Record<string, ProviderConfig[]> = {};
        projects.forEach((project, index) => {
          summaries[project.id] = results[index];
        });
        this.providersByProject.set(summaries);
      },
      error: () => undefined,
    });
  }

}
