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
      {
        path: 'datasets',
        loadComponent: () =>
          import('./features/datasets/datasets.component').then(
            (m) => m.DatasetsComponent,
          ),
      },
      {
        path: 'evaluations',
        loadComponent: () =>
          import('./features/evaluations/evaluations.component').then(
            (m) => m.EvaluationsComponent,
          ),
      },
      {
        path: 'observability',
        loadComponent: () =>
          import('./features/observability/observability.component').then(
            (m) => m.ObservabilityComponent,
          ),
      },
      {
        path: 'observability/traces/:id',
        loadComponent: () =>
          import('./features/observability/trace-detail.component').then(
            (m) => m.TraceDetailComponent,
          ),
      },
      {
        path: 'security',
        loadComponent: () =>
          import('./features/security/security.component').then(
            (m) => m.SecurityComponent,
          ),
      },
      {
        path: 'analytics',
        loadComponent: () =>
          import('./features/analytics/analytics.component').then(
            (m) => m.AnalyticsComponent,
          ),
      },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },
  { path: 'status', redirectTo: 'dashboard' },
  { path: '**', redirectTo: '' },
];
