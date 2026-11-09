import { Routes } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';
import { ShellComponent } from './shared/ui/shell.component';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    component: ShellComponent,
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(
            (m) => m.DashboardComponent,
          ),
      },
      {
        path: 'workspaces',
        loadComponent: () =>
          import('./features/workspaces/workspaces.component').then(
            (m) => m.WorkspacesComponent,
          ),
      },
      {
        path: 'playground',
        loadComponent: () =>
          import('./features/playground/playground.component').then(
            (m) => m.PlaygroundComponent,
          ),
      },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },
  { path: 'status', redirectTo: 'dashboard' },
  { path: '**', redirectTo: '' },
];
