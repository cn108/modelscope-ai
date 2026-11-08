import { Routes } from '@angular/router';

import { DashboardComponent } from './features/dashboard/dashboard.component';

/**
 * Feature routes are lazy-loaded per specification section 6.
 * Feature modules arrive with milestones 2-8; dashboard verifies the API seam now.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', component: DashboardComponent },
  // e.g. { path: 'workspaces', loadChildren: () => import('./features/workspaces/routes').then(m => m.ROUTES) }
];
