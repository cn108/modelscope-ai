import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import {
  Membership,
  Project,
  Workspace,
  WorkspaceRole,
} from '../../shared/models/workspace.model';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from './workspace.service';

@Component({
  selector: 'msa-workspaces',
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <main class="mx-auto max-w-6xl p-6">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold tracking-tight">Workspaces</h1>
          <p class="mt-1 text-sm text-slate-500">
            Manage projects, members and role-based access.
          </p>
        </div>
        <form
          [formGroup]="workspaceForm"
          (ngSubmit)="createWorkspace()"
          class="flex gap-2"
        >
          <input
            formControlName="name"
            type="text"
            placeholder="New workspace"
            class="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            [disabled]="busy()"
            class="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            Create
          </button>
        </form>
      </div>

      @if (error()) {
        <p class="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {{ error() }}
        </p>
      }

      @if (loading()) {
        <p class="mt-8 text-sm text-slate-400">Loading workspaces…</p>
      } @else {
        <div class="mt-6 grid gap-6 md:grid-cols-[16rem_1fr]">
          <aside class="space-y-1">
            @for (workspace of workspaces(); track workspace.id) {
              <button
                type="button"
                (click)="selectWorkspace(workspace)"
                class="w-full rounded-md px-3 py-2 text-left text-sm"
                [class]="
                  workspace.id === selected()?.id
                    ? 'bg-slate-900 text-white'
                    : 'text-slate-700 hover:bg-slate-100'
                "
              >
                <span class="block font-medium">{{ workspace.name }}</span>
                <span class="block text-xs opacity-70">{{ workspace.role }}</span>
              </button>
            } @empty {
              <p class="text-sm text-slate-400">
                No workspaces yet. Create one above.
              </p>
            }
          </aside>

          <section>
            @if (selected(); as workspace) {
              <header class="flex items-center justify-between">
                <h2 class="text-lg font-semibold">{{ workspace.name }}</h2>
                <span
                  class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600"
                >
                  {{ workspace.role }}
                </span>
              </header>

              <div class="mt-4 grid gap-6 lg:grid-cols-2">
                <div class="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 class="font-medium">Projects</h3>
                  <form
                    [formGroup]="projectForm"
                    (ngSubmit)="createProject()"
                    class="mt-3 space-y-2"
                  >
                    <input
                      formControlName="name"
                      type="text"
                      placeholder="Project name"
                      class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                    />
                    <input
                      formControlName="description"
                      type="text"
                      placeholder="Description (optional)"
                      class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                    />
                    <button
                      type="submit"
                      [disabled]="busy() || !canCreateProject"
                      class="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                    >
                      Add project
                    </button>
                  </form>

                  <ul class="mt-4 space-y-2">
                    @for (project of projects(); track project.id) {
                      <li
                        class="rounded-md border border-slate-100 px-3 py-2 text-sm"
                      >
                        <span class="font-medium">{{ project.name }}</span>
                        @if (project.description) {
                          <span class="block text-xs text-slate-500">
                            {{ project.description }}
                          </span>
                        }
                      </li>
                    } @empty {
                      <li class="text-sm text-slate-400">No projects yet.</li>
                    }
                  </ul>
                </div>

                <div class="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 class="font-medium">Members</h3>
                  @if (canManage) {
                    <form
                      [formGroup]="memberForm"
                      (ngSubmit)="addMember()"
                      class="mt-3 space-y-2"
                    >
                      <input
                        formControlName="email"
                        type="email"
                        placeholder="member@example.com"
                        class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                      />
                      <div class="flex gap-2">
                        <select
                          formControlName="role"
                          class="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                        >
                          @for (role of assignableRoles; track role) {
                            <option [value]="role">{{ role }}</option>
                          }
                        </select>
                        <button
                          type="submit"
                          [disabled]="busy()"
                          class="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                        >
                          Add
                        </button>
                      </div>
                    </form>
                  }

                  <ul class="mt-4 space-y-2">
                    @for (member of members(); track member.id) {
                      <li
                        class="flex items-center justify-between gap-2 rounded-md border border-slate-100 px-3 py-2 text-sm"
                      >
                        <div>
                          <span class="font-medium">{{ member.user.email }}</span>
                          <span class="block text-xs text-slate-500">
                            {{ member.user.display_name || 'No display name' }}
                          </span>
                        </div>

                        @if (canEditMember(member)) {
                          <div class="flex items-center gap-2">
                            <select
                              [value]="member.role"
                              (change)="changeRole(member, $event)"
                              class="rounded-md border border-slate-300 px-2 py-1 text-xs"
                            >
                              @for (role of assignableRoles; track role) {
                                <option [value]="role" [selected]="role === member.role">
                                  {{ role }}
                                </option>
                              }
                            </select>
                            <button
                              type="button"
                              (click)="removeMember(member)"
                              class="text-xs text-red-600 hover:text-red-700"
                            >
                              Remove
                            </button>
                          </div>
                        } @else {
                          <span
                            class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                          >
                            {{ member.role }}
                          </span>
                        }
                      </li>
                    } @empty {
                      <li class="text-sm text-slate-400">No members yet.</li>
                    }
                  </ul>
                </div>
              </div>
            } @else {
              <p class="text-sm text-slate-400">
                Select a workspace to see its projects and members.
              </p>
            }
          </section>
        </div>
      }
    </main>
  `,
})
export class WorkspacesComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly fb = inject(FormBuilder);

  readonly workspaces = signal<Workspace[]>([]);
  readonly selected = signal<Workspace | null>(null);
  readonly projects = signal<Project[]>([]);
  readonly members = signal<Membership[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

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

  selectWorkspace(workspace: Workspace): void {
    this.selected.set(workspace);
    this.error.set(null);
    this.loadWorkspaceData(workspace.id);
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
        if (workspace) {
          this.loadWorkspaceData(workspace.id);
        } else {
          this.projects.set([]);
          this.members.set([]);
        }
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
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
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }
}
