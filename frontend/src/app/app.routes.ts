import { Routes } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'workspaces',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/workspaces/workspaces.component').then(
        (m) => m.WorkspacesComponent,
      ),
  },
  {
    path: 'status',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then(
        (m) => m.DashboardComponent,
      ),
  },
  { path: '', pathMatch: 'full', redirectTo: 'workspaces' },
  { path: '**', redirectTo: '' },
];
