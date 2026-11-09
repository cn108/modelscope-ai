import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface PromptVersion {
  id: string;
  version_number: number;
  system_prompt: string;
  user_prompt: string;
  parameters: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
}

export interface SavedPrompt {
  id: string;
  project: string;
  name: string;
  description: string;
  current_version: PromptVersion | null;
  version_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptInput {
  name: string;
  description?: string;
  system_prompt: string;
  user_prompt: string;
  parameters: Record<string, unknown>;
}

export interface ModelSelection {
  provider: string;
  model_id: string;
  parameters?: Record<string, unknown>;
}

export interface ExecutionInput {
  system_prompt: string;
  user_prompt: string;
  parameters: Record<string, unknown>;
  prompt?: string | null;
  models: ModelSelection[];
}

export interface ExecutionError {
  category: string;
  message: string;
}

export interface ExecutionResult {
  id: string;
  position: number;
  provider: string | null;
  provider_name: string;
  provider_kind: string;
  model_id: string;
  content: string;
  input_tokens: number | null;
  output_tokens: number | null;
  tokens_are_provider_reported: boolean;
  latency_ms: number | null;
  finish_reason: string;
  request_id: string;
  estimated_cost: string | null;
  cost_currency: string;
  status: 'succeeded' | 'failed';
  error: ExecutionError | null;
  created_at: string;
}

export interface Execution {
  id: string;
  project: string;
  prompt: string | null;
  prompt_version: number | null;
  mode: 'single' | 'compare';
  system_prompt: string;
  user_prompt: string;
  parameters: Record<string, unknown>;
  status: 'succeeded' | 'partial' | 'failed';
  created_by: string | null;
  created_at: string;
  results: ExecutionResult[];
}

@Injectable({ providedIn: 'root' })
export class PlaygroundService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  prompts(projectId: string): Observable<SavedPrompt[]> {
    return this.http.get<SavedPrompt[]>(`${this.base}/projects/${projectId}/prompts/`);
  }

  createPrompt(projectId: string, input: PromptInput): Observable<SavedPrompt> {
    return this.http.post<SavedPrompt>(
      `${this.base}/projects/${projectId}/prompts/`,
      input,
    );
  }

  updatePrompt(
    promptId: string,
    input: Partial<PromptInput>,
  ): Observable<SavedPrompt> {
    return this.http.patch<SavedPrompt>(`${this.base}/prompts/${promptId}/`, input);
  }

  deletePrompt(promptId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/prompts/${promptId}/`);
  }

  duplicatePrompt(promptId: string): Observable<SavedPrompt> {
    return this.http.post<SavedPrompt>(
      `${this.base}/prompts/${promptId}/duplicate/`,
      {},
    );
  }

  versions(promptId: string): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(
      `${this.base}/prompts/${promptId}/versions/`,
    );
  }

  restore(promptId: string, versionNumber: number): Observable<SavedPrompt> {
    return this.http.post<SavedPrompt>(
      `${this.base}/prompts/${promptId}/versions/restore/`,
      { version_number: versionNumber },
    );
  }

  executions(projectId: string): Observable<Execution[]> {
    return this.http.get<Execution[]>(
      `${this.base}/projects/${projectId}/executions/`,
    );
  }

  run(projectId: string, input: ExecutionInput): Observable<Execution> {
    return this.http.post<Execution>(
      `${this.base}/projects/${projectId}/executions/`,
      input,
    );
  }

  rerun(executionId: string): Observable<Execution> {
    return this.http.post<Execution>(`${this.base}/executions/${executionId}/rerun/`, {});
  }
}
