import { HttpErrorResponse } from '@angular/common/http';

import { ApiErrorBody } from './models/auth.model';

export function apiErrorMessage(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) {
    return 'Request failed.';
  }
  const body = error.error as ApiErrorBody | null;
  const details = body?.error?.details;
  if (details) {
    const first = Object.values(details)[0];
    if (Array.isArray(first) && first.length > 0) {
      return String(first[0]);
    }
  }
  return body?.error?.message ?? error.message ?? 'Request failed.';
}
