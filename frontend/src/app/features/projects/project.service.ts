import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated, Project } from '../../shared/models/workspace.model';

@Injectable({ providedIn: 'root' })
export class ProjectService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/projects`;

  list(workspaceId: string): Observable<Paginated<Project>> {
    return this.http.get<Paginated<Project>>(`${this.base}/`, {
      params: new HttpParams().set('workspace', workspaceId),
    });
  }

  create(
    workspaceId: string,
    name: string,
    description = '',
  ): Observable<Project> {
    return this.http.post<Project>(`${this.base}/`, {
      workspace: workspaceId,
      name,
      description,
    });
  }
}
