import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  Membership,
  Paginated,
  Workspace,
  WorkspaceRole,
} from '../../shared/models/workspace.model';
import { AuditEventRow } from '../settings/settings.service';

@Injectable({ providedIn: 'root' })
export class WorkspaceService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/workspaces`;

  list(): Observable<Paginated<Workspace>> {
    return this.http.get<Paginated<Workspace>>(`${this.base}/`);
  }

  create(name: string): Observable<Workspace> {
    return this.http.post<Workspace>(`${this.base}/`, { name });
  }

  update(
    workspaceId: string,
    input: { name?: string; settings?: Record<string, unknown> },
  ): Observable<Workspace> {
    return this.http.patch<Workspace>(`${this.base}/${workspaceId}/`, input);
  }

  delete(workspaceId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${workspaceId}/`);
  }

  exportData(workspaceId: string): Observable<Blob> {
    return this.http.get(`${this.base}/${workspaceId}/export/`, {
      responseType: 'blob',
    });
  }

  audit(workspaceId: string): Observable<Paginated<AuditEventRow>> {
    return this.http.get<Paginated<AuditEventRow>>(
      `${this.base}/${workspaceId}/audit/`,
    );
  }

  members(workspaceId: string): Observable<Paginated<Membership>> {
    return this.http.get<Paginated<Membership>>(
      `${this.base}/${workspaceId}/members/`,
    );
  }

  addMember(
    workspaceId: string,
    email: string,
    role: WorkspaceRole,
  ): Observable<Membership> {
    return this.http.post<Membership>(`${this.base}/${workspaceId}/members/`, {
      email,
      role,
    });
  }

  updateMemberRole(
    workspaceId: string,
    membershipId: string,
    role: WorkspaceRole,
  ): Observable<Membership> {
    return this.http.patch<Membership>(
      `${this.base}/${workspaceId}/members/${membershipId}/`,
      { role },
    );
  }

  removeMember(workspaceId: string, membershipId: string): Observable<void> {
    return this.http.delete<void>(
      `${this.base}/${workspaceId}/members/${membershipId}/`,
    );
  }
}
