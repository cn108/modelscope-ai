import { User } from './auth.model';

export type WorkspaceRole = 'owner' | 'admin' | 'member' | 'viewer';

export interface Workspace {
  id: string;
  name: string;
  owner: string;
  settings: Record<string, unknown>;
  role: WorkspaceRole;
  created_at: string;
  updated_at: string;
}

export interface Membership {
  id: string;
  user: User;
  role: WorkspaceRole;
  created_at: string;
}

export interface Project {
  id: string;
  workspace: string;
  name: string;
  description: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
