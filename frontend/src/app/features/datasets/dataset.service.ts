import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../../shared/models/workspace.model';

export interface Dataset {
  id: string;
  project: string;
  name: string;
  description: string;
  version: number;
  record_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetRecord {
  id: string;
  dataset: string;
  position: number;
  input: string;
  expected_output: string;
  context: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RecordInput {
  input: string;
  expected_output?: string;
  context?: string[];
  metadata?: Record<string, unknown>;
}

export interface ImportRowError {
  row: number;
  field: string;
  message: string;
}

export interface ImportResult {
  imported: number;
  version: number;
  mode: 'append' | 'replace';
}

@Injectable({ providedIn: 'root' })
export class DatasetService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  list(projectId: string): Observable<Dataset[]> {
    return this.http.get<Dataset[]>(`${this.base}/projects/${projectId}/datasets/`);
  }

  create(projectId: string, name: string, description = ''): Observable<Dataset> {
    return this.http.post<Dataset>(`${this.base}/projects/${projectId}/datasets/`, {
      name,
      description,
    });
  }

  get(datasetId: string): Observable<Dataset> {
    return this.http.get<Dataset>(`${this.base}/datasets/${datasetId}/`);
  }

  update(
    datasetId: string,
    input: { name?: string; description?: string },
  ): Observable<Dataset> {
    return this.http.patch<Dataset>(`${this.base}/datasets/${datasetId}/`, input);
  }

  delete(datasetId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/datasets/${datasetId}/`);
  }

  records(datasetId: string, page = 1): Observable<Paginated<DatasetRecord>> {
    return this.http.get<Paginated<DatasetRecord>>(
      `${this.base}/datasets/${datasetId}/records/`,
      { params: new HttpParams().set('page', page) },
    );
  }

  createRecord(datasetId: string, input: RecordInput): Observable<DatasetRecord> {
    return this.http.post<DatasetRecord>(
      `${this.base}/datasets/${datasetId}/records/`,
      input,
    );
  }

  updateRecord(recordId: string, input: RecordInput): Observable<DatasetRecord> {
    return this.http.patch<DatasetRecord>(
      `${this.base}/dataset-records/${recordId}/`,
      input,
    );
  }

  deleteRecord(recordId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/dataset-records/${recordId}/`);
  }

  importFile(
    datasetId: string,
    file: File,
    mode: 'append' | 'replace',
  ): Observable<ImportResult> {
    const body = new FormData();
    body.append('file', file);
    body.append('mode', mode);
    return this.http.post<ImportResult>(
      `${this.base}/datasets/${datasetId}/import/`,
      body,
    );
  }
}
