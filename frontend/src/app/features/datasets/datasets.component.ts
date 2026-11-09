import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

import { apiErrorMessage } from '../../shared/api-error';
import { Paginated, Project, Workspace } from '../../shared/models/workspace.model';
import { IconComponent } from '../../shared/ui/icon.component';
import { ProjectService } from '../projects/project.service';
import { WorkspaceService } from '../workspaces/workspace.service';
import {
  Dataset,
  DatasetRecord,
  DatasetService,
  ImportRowError,
} from './dataset.service';

interface ProjectOption extends Project {
  workspaceName: string;
}

const PAGE_SIZE = 50;

@Component({
  selector: 'msa-datasets',
  standalone: true,
  imports: [DatePipe, IconComponent],
  template: `
    <div class="msa-page">
      <header class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="msa-h1">Datasets</h1>
          <p class="msa-sub">
            Test cases your evaluations run against. Every change bumps the
            dataset version, and past evaluation runs keep their snapshot.
          </p>
        </div>
        <label class="flex items-center gap-2 text-xs text-muted">
          <span class="whitespace-nowrap font-medium">Project</span>
          <select
            class="msa-input min-w-[220px]"
            [value]="selectedProjectId()"
            (change)="selectProject($any($event.target).value)"
            aria-label="Select project"
          >
            @for (project of projects(); track project.id) {
              <option [value]="project.id">
                {{ project.workspaceName }} · {{ project.name }}
              </option>
            }
          </select>
        </label>
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
      @if (notice()) {
        <p
          class="msa-card mt-5 flex items-start gap-2 border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700"
          role="status"
        >
          <msa-icon name="check-circle" [size]="16" />
          <span>{{ notice() }}</span>
        </p>
      }

      @if (loading()) {
        <div class="mt-6 grid gap-4 xl:grid-cols-[300px_1fr]">
          <div class="msa-card p-5">
            <div class="msa-skeleton h-3 w-28"></div>
            <div class="msa-skeleton mt-4 h-9 w-full"></div>
            <div class="msa-skeleton mt-2 h-9 w-full"></div>
          </div>
          <div class="msa-card p-5">
            <div class="msa-skeleton h-4 w-40"></div>
            <div class="msa-skeleton mt-4 h-24 w-full"></div>
          </div>
        </div>
      } @else if (!projects().length) {
        <div class="msa-card mt-6 flex flex-col items-center p-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-soft text-brand">
            <msa-icon name="database" [size]="26" />
          </span>
          <p class="mt-4 text-base font-semibold text-ink">Create a project first</p>
          <p class="mt-1 max-w-sm text-sm text-muted">
            Datasets live inside a project. Create one in Workspaces, then come
            back to add test cases.
          </p>
        </div>
      } @else {
        <div class="mt-6 grid gap-4 xl:grid-cols-[300px_1fr]">
          <div class="space-y-4">
            <section class="msa-card p-4">
              <h2 class="msa-section-title">New dataset</h2>
              <div class="mt-3 space-y-2">
                <input
                  class="msa-input"
                  placeholder="Dataset name"
                  aria-label="New dataset name"
                  [value]="newName()"
                  (input)="newName.set($any($event.target).value)"
                />
                <textarea
                  class="msa-input resize-y"
                  rows="2"
                  placeholder="What does this dataset cover?"
                  aria-label="New dataset description"
                  [value]="newDescription()"
                  (input)="newDescription.set($any($event.target).value)"
                ></textarea>
                <button
                  type="button"
                  class="msa-btn-primary w-full justify-center"
                  [disabled]="busy()"
                  (click)="createDataset()"
                >
                  <msa-icon name="plus" [size]="15" /> Create dataset
                </button>
              </div>
            </section>

            <section class="msa-card overflow-hidden">
              <div class="msa-card-header">
                <h2 class="msa-section-title">Datasets</h2>
                <span class="msa-badge bg-slate-50 text-slate-500">
                  {{ datasets().length }}
                </span>
              </div>
              @if (datasets().length) {
                <ul class="divide-y divide-line">
                  @for (dataset of datasets(); track dataset.id) {
                    <li>
                      <button
                        type="button"
                        class="flex w-full items-center gap-2 px-4 py-3 text-left"
                        [class]="selectedDatasetId() === dataset.id ? 'bg-brand-soft/40' : ''"
                        (click)="selectDataset(dataset.id)"
                      >
                        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-slate-400 ring-1 ring-line">
                          <msa-icon name="database" [size]="15" />
                        </span>
                        <span class="min-w-0 flex-1">
                          <span class="block truncate text-sm font-medium text-ink">
                            {{ dataset.name }}
                          </span>
                          <span class="block text-[11px] text-slate-400">
                            v{{ dataset.version }} · {{ dataset.record_count }}
                            record{{ dataset.record_count === 1 ? '' : 's' }}
                          </span>
                        </span>
                      </button>
                    </li>
                  }
                </ul>
              } @else {
                <p class="px-4 py-8 text-center text-sm text-muted">
                  No datasets yet. Create one to start importing test cases.
                </p>
              }
            </section>
          </div>

          @if (dataset(); as current) {
            <div class="space-y-4">
              <section class="msa-card p-5">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h2 class="text-lg font-semibold tracking-tight text-ink">
                      {{ current.name }}
                    </h2>
                    <p class="text-xs text-muted">
                      Version {{ current.version }} ·
                      {{ current.record_count }} record{{
                        current.record_count === 1 ? '' : 's'
                      }}
                      · created {{ current.created_at | date: 'mediumDate' }}
                    </p>
                  </div>
                  <button
                    type="button"
                    class="msa-btn-ghost text-rose-600"
                    [disabled]="busy()"
                    (click)="deleteDataset(current)"
                  >
                    <msa-icon name="trash" [size]="14" /> Delete
                  </button>
                </div>

                <div class="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <input
                    class="msa-input"
                    aria-label="Dataset name"
                    [value]="editName()"
                    (input)="editName.set($any($event.target).value)"
                  />
                  <input
                    class="msa-input"
                    aria-label="Dataset description"
                    placeholder="Description"
                    [value]="editDescription()"
                    (input)="editDescription.set($any($event.target).value)"
                  />
                  <button
                    type="button"
                    class="msa-btn-secondary whitespace-nowrap"
                    [disabled]="busy()"
                    (click)="saveDataset(current)"
                  >
                    Save details
                  </button>
                </div>
              </section>

              <section class="msa-card p-5">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 class="msa-section-title">Import test cases</h2>
                    <p class="text-xs text-muted">
                      JSON array, JSONL, or CSV with an
                      <code class="text-[11px]">input</code> column and optional
                      <code class="text-[11px]">expected_output</code>,
                      <code class="text-[11px]">context</code> and
                      <code class="text-[11px]">metadata</code>.
                    </p>
                  </div>
                  <span class="msa-badge bg-slate-50 text-slate-500">max 500 rows</span>
                </div>

                <div class="mt-4 flex flex-wrap items-center gap-2">
                  <input
                    type="file"
                    accept=".json,.jsonl,.ndjson,.csv"
                    aria-label="Dataset file"
                    class="text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-3 file:py-2 file:text-xs file:font-medium file:text-white"
                    (change)="onFileSelected($event)"
                  />
                  <select
                    class="msa-input max-w-[150px]"
                    aria-label="Import mode"
                    [value]="importMode()"
                    (change)="importMode.set($any($event.target).value)"
                  >
                    <option value="append">Append</option>
                    <option value="replace">Replace all</option>
                  </select>
                  <button
                    type="button"
                    class="msa-btn-primary"
                    [disabled]="busy() || !selectedFile()"
                    (click)="importDataset(current)"
                  >
                    <msa-icon name="upload" [size]="15" /> Import file
                  </button>
                </div>

                @if (importErrors().length) {
                  <div class="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3">
                    <p class="text-xs font-semibold text-rose-800">
                      {{ importErrorCount() }} problem{{
                        importErrorCount() === 1 ? '' : 's'
                      }} found — nothing was imported.
                    </p>
                    <ul class="mt-2 max-h-48 space-y-1 overflow-y-auto text-[11px] text-rose-700">
                      @for (problem of importErrors(); track $index) {
                        <li>
                          Row {{ problem.row }} · {{ problem.field }}:
                          {{ problem.message }}
                        </li>
                      }
                    </ul>
                  </div>
                }
              </section>

              <section class="msa-card overflow-hidden">
                <div class="msa-card-header">
                  <div>
                    <h2 class="msa-section-title">Test cases</h2>
                    <p class="text-xs text-muted">
                      Edit a record to add or change its expected answer and
                      context.
                    </p>
                  </div>
                  <span class="msa-badge bg-slate-50 text-slate-500">
                    {{ recordCount() }}
                  </span>
                </div>

                <div class="border-b border-line bg-canvas/40 p-4">
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {{ editingRecordId() ? 'Edit record' : 'Add record' }}
                    </p>
                    @if (editingRecordId()) {
                      <button type="button" class="msa-btn-ghost" (click)="cancelRecordEdit()">
                        <msa-icon name="close" [size]="13" /> Cancel edit
                      </button>
                    }
                  </div>
                  <div class="mt-2 grid gap-2 lg:grid-cols-2">
                    <div>
                      <label class="msa-label" for="record-input">Input</label>
                      <textarea
                        id="record-input"
                        class="msa-input resize-y"
                        rows="3"
                        placeholder="The prompt sent to every model"
                        [value]="recordInput()"
                        (input)="recordInput.set($any($event.target).value)"
                      ></textarea>
                    </div>
                    <div>
                      <label class="msa-label" for="record-expected">
                        Expected answer (optional)
                      </label>
                      <textarea
                        id="record-expected"
                        class="msa-input resize-y"
                        rows="3"
                        placeholder="Reference answer for exact-match style metrics"
                        [value]="recordExpected()"
                        (input)="recordExpected.set($any($event.target).value)"
                      ></textarea>
                    </div>
                  </div>
                  <div class="mt-2">
                    <label class="msa-label" for="record-context">
                      Retrieval context (optional, one passage per line)
                    </label>
                    <textarea
                      id="record-context"
                      class="msa-input resize-y"
                      rows="2"
                      placeholder="Passages used by faithfulness and contextual relevancy"
                      [value]="recordContext()"
                      (input)="recordContext.set($any($event.target).value)"
                    ></textarea>
                  </div>
                  <button
                    type="button"
                    class="msa-btn-primary mt-3"
                    [disabled]="busy()"
                    (click)="saveRecord(current)"
                  >
                    <msa-icon [name]="editingRecordId() ? 'check' : 'plus'" [size]="15" />
                    {{ editingRecordId() ? 'Save record' : 'Add record' }}
                  </button>
                </div>

                @if (records().length) {
                  <div class="overflow-x-auto">
                    <table class="msa-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Input</th>
                          <th>Expected</th>
                          <th>Context</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        @for (record of records(); track record.id) {
                          <tr>
                            <td class="text-xs text-slate-400">{{ record.position }}</td>
                            <td class="max-w-[280px]">
                              <p class="line-clamp-2 text-sm text-slate-700">
                                {{ record.input }}
                              </p>
                            </td>
                            <td class="max-w-[200px]">
                              <p class="line-clamp-2 text-xs text-slate-500">
                                {{ record.expected_output || '—' }}
                              </p>
                            </td>
                            <td class="text-xs text-slate-500">
                              {{ record.context.length }} passage{{
                                record.context.length === 1 ? '' : 's'
                              }}
                            </td>
                            <td class="text-right">
                              <div class="flex justify-end gap-1">
                                <button
                                  type="button"
                                  class="msa-icon-btn"
                                  title="Edit record"
                                  (click)="editRecord(record)"
                                >
                                  <msa-icon name="edit" [size]="14" />
                                </button>
                                <button
                                  type="button"
                                  class="msa-icon-btn text-rose-600"
                                  title="Delete record"
                                  (click)="deleteRecord(record)"
                                >
                                  <msa-icon name="trash" [size]="14" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                  @if (recordCount() > pageSize) {
                    <div class="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-muted">
                      <span>
                        Page {{ recordPage() }} of {{ recordPages() }}
                      </span>
                      <div class="flex gap-2">
                        <button
                          type="button"
                          class="msa-btn-ghost"
                          [disabled]="recordPage() <= 1"
                          (click)="loadRecords(current.id, recordPage() - 1)"
                        >
                          Previous
                        </button>
                        <button
                          type="button"
                          class="msa-btn-ghost"
                          [disabled]="recordPage() >= recordPages()"
                          (click)="loadRecords(current.id, recordPage() + 1)"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  }
                } @else {
                  <p class="px-4 py-8 text-center text-sm text-muted">
                    No test cases yet. Add one above or import a file.
                  </p>
                }
              </section>
            </div>
          } @else {
            <div class="msa-card flex flex-col items-center justify-center p-12 text-center">
              <span class="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-400">
                <msa-icon name="database" [size]="22" />
              </span>
              <p class="mt-3 text-sm font-medium text-ink">Select a dataset</p>
              <p class="mt-1 max-w-sm text-sm text-muted">
                Choose a dataset on the left to inspect its records, or create a
                new one.
              </p>
            </div>
          }
        </div>
      }
    </div>
  `,
})
export class DatasetsComponent implements OnInit {
  private readonly workspaceService = inject(WorkspaceService);
  private readonly projectService = inject(ProjectService);
  private readonly datasetService = inject(DatasetService);

  readonly pageSize = PAGE_SIZE;

  readonly projects = signal<ProjectOption[]>([]);
  readonly selectedProjectId = signal('');
  readonly datasets = signal<Dataset[]>([]);
  readonly selectedDatasetId = signal('');
  readonly dataset = signal<Dataset | null>(null);
  readonly records = signal<DatasetRecord[]>([]);
  readonly recordPage = signal(1);
  readonly recordCount = signal(0);

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  readonly newName = signal('');
  readonly newDescription = signal('');
  readonly editName = signal('');
  readonly editDescription = signal('');

  readonly editingRecordId = signal<string | null>(null);
  readonly recordInput = signal('');
  readonly recordExpected = signal('');
  readonly recordContext = signal('');

  readonly importMode = signal<'append' | 'replace'>('append');
  readonly selectedFile = signal<File | null>(null);
  readonly importErrors = signal<ImportRowError[]>([]);
  readonly importErrorCount = signal(0);

  ngOnInit(): void {
    this.loadProjects();
  }

  selectProject(projectId: string): void {
    if (!projectId || projectId === this.selectedProjectId()) {
      return;
    }
    this.selectedProjectId.set(projectId);
    this.selectedDatasetId.set('');
    this.dataset.set(null);
    this.records.set([]);
    this.resetMessages();
    this.loadDatasets(projectId);
  }

  selectDataset(datasetId: string): void {
    this.selectedDatasetId.set(datasetId);
    this.importErrors.set([]);
    this.importErrorCount.set(0);
    this.cancelRecordEdit();
    this.loadDataset(datasetId);
    this.loadRecords(datasetId, 1);
  }

  createDataset(): void {
    const projectId = this.selectedProjectId();
    const name = this.newName().trim();
    if (!projectId) {
      return;
    }
    if (!name) {
      this.error.set('Give the dataset a name.');
      return;
    }
    this.busy.set(true);
    this.resetMessages();
    this.datasetService.create(projectId, name, this.newDescription().trim()).subscribe({
      next: (dataset) => {
        this.busy.set(false);
        this.newName.set('');
        this.newDescription.set('');
        this.datasets.update((rows) => [...rows, dataset].sort((a, b) => a.name.localeCompare(b.name)));
        this.notice.set(`Created “${dataset.name}”.`);
        this.selectDataset(dataset.id);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  saveDataset(dataset: Dataset): void {
    const name = this.editName().trim();
    if (!name) {
      this.error.set('The dataset needs a name.');
      return;
    }
    this.busy.set(true);
    this.resetMessages();
    this.datasetService
      .update(dataset.id, { name, description: this.editDescription().trim() })
      .subscribe({
        next: (updated) => {
          this.busy.set(false);
          this.applyDataset(updated);
          this.notice.set('Dataset details saved.');
        },
        error: (error: unknown) => {
          this.busy.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  deleteDataset(dataset: Dataset): void {
    if (!globalThis.confirm(`Delete “${dataset.name}” and all of its records?`)) {
      return;
    }
    this.busy.set(true);
    this.resetMessages();
    this.datasetService.delete(dataset.id).subscribe({
      next: () => {
        this.busy.set(false);
        this.datasets.update((rows) => rows.filter((row) => row.id !== dataset.id));
        this.selectedDatasetId.set('');
        this.dataset.set(null);
        this.records.set([]);
        this.notice.set('Dataset deleted. Past evaluations keep their snapshots.');
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile.set(input.files?.[0] ?? null);
    this.importErrors.set([]);
    this.importErrorCount.set(0);
  }

  importDataset(dataset: Dataset): void {
    const file = this.selectedFile();
    if (!file) {
      return;
    }
    this.busy.set(true);
    this.resetMessages();
    this.datasetService.importFile(dataset.id, file, this.importMode()).subscribe({
      next: (result) => {
        this.busy.set(false);
        this.selectedFile.set(null);
        this.notice.set(
          `Imported ${result.imported} record${result.imported === 1 ? '' : 's'} (version ${result.version}).`,
        );
        this.loadDataset(dataset.id);
        this.loadRecords(dataset.id, 1);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        const details = (error as { error?: { error?: { details?: { errors?: ImportRowError[]; error_count?: number } } } })
          .error?.error?.details;
        if (details?.errors) {
          this.importErrors.set(details.errors);
          this.importErrorCount.set(details.error_count ?? details.errors.length);
          return;
        }
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  editRecord(record: DatasetRecord): void {
    this.editingRecordId.set(record.id);
    this.recordInput.set(record.input);
    this.recordExpected.set(record.expected_output);
    this.recordContext.set(record.context.join('\n'));
  }

  cancelRecordEdit(): void {
    this.editingRecordId.set(null);
    this.recordInput.set('');
    this.recordExpected.set('');
    this.recordContext.set('');
  }

  saveRecord(dataset: Dataset): void {
    const input = this.recordInput().trim();
    if (!input) {
      this.error.set('A record needs an input.');
      return;
    }
    const payload = {
      input,
      expected_output: this.recordExpected().trim(),
      context: this.recordContext()
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    };
    const recordId = this.editingRecordId();
    this.busy.set(true);
    this.resetMessages();
    const request = recordId
      ? this.datasetService.updateRecord(recordId, payload)
      : this.datasetService.createRecord(dataset.id, payload);
    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set(recordId ? 'Record updated.' : 'Record added.');
        this.cancelRecordEdit();
        this.loadDataset(dataset.id);
        this.loadRecords(dataset.id, recordId ? this.recordPage() : 1);
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  deleteRecord(record: DatasetRecord): void {
    const datasetId = this.selectedDatasetId();
    if (!globalThis.confirm(`Delete record #${record.position}?`)) {
      return;
    }
    this.busy.set(true);
    this.resetMessages();
    this.datasetService.deleteRecord(record.id).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set('Record deleted.');
        this.loadDataset(datasetId);
        this.loadRecords(datasetId, this.recordPage());
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  loadRecords(datasetId: string, page: number): void {
    this.datasetService.records(datasetId, page).subscribe({
      next: (result) => {
        this.records.set(result.results);
        this.recordCount.set(result.count);
        this.recordPage.set(page);
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  recordPages(): number {
    return Math.max(1, Math.ceil(this.recordCount() / this.pageSize));
  }

  private loadProjects(): void {
    this.loading.set(true);
    this.workspaceService.list().subscribe({
      next: (page) => {
        if (!page.results.length) {
          this.loading.set(false);
          return;
        }
        forkJoin(
          page.results.map((workspace) =>
            this.projectService.list(workspace.id).pipe(
              map((projects) =>
                projects.results.map((project) => ({
                  ...project,
                  workspaceName: workspace.name,
                })),
              ),
              catchError(() => of([] as ProjectOption[])),
            ),
          ),
        ).subscribe({
          next: (lists) => {
            const projects = lists.flat();
            this.projects.set(projects);
            this.loading.set(false);
            const first = projects[0];
            if (first) {
              this.selectedProjectId.set(first.id);
              this.loadDatasets(first.id);
            }
          },
          error: (error: unknown) => {
            this.loading.set(false);
            this.error.set(apiErrorMessage(error));
          },
        });
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private loadDatasets(projectId: string): void {
    this.datasetService.list(projectId).subscribe({
      next: (datasets) => {
        this.datasets.set(datasets);
        const existing = datasets.find((row) => row.id === this.selectedDatasetId());
        const next = existing ?? datasets[0];
        if (next) {
          this.selectDataset(next.id);
        }
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private loadDataset(datasetId: string): void {
    this.datasetService.get(datasetId).subscribe({
      next: (dataset) => this.applyDataset(dataset),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private applyDataset(dataset: Dataset): void {
    this.dataset.set(dataset);
    this.editName.set(dataset.name);
    this.editDescription.set(dataset.description);
    this.datasets.update((rows) =>
      rows.map((row) =>
        row.id === dataset.id
          ? { ...row, name: dataset.name, description: dataset.description, version: dataset.version, record_count: dataset.record_count }
          : row,
      ),
    );
  }

  private resetMessages(): void {
    this.error.set(null);
    this.notice.set(null);
  }
}
