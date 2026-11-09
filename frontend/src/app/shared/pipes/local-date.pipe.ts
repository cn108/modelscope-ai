import { DatePipe } from '@angular/common';
import { Pipe, PipeTransform, inject } from '@angular/core';

import { AuthService } from '../../core/authentication/auth.service';

/**
 * Formats dates using the signed-in user's timezone and date-format preference.
 * Unknown or missing preferences fall back to the original Angular format.
 */
@Pipe({ name: 'msaDate', standalone: true, pure: false })
export class LocalDatePipe implements PipeTransform {
  private readonly auth = inject(AuthService);
  private readonly datePipe = new DatePipe('en-US');

  transform(
    value: string | number | Date | null | undefined,
    format = 'medium',
  ): string | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const preferences = this.auth.user()?.preferences;
    const timezone = preferences?.timezone || undefined;
    const dateOnly = format.toLowerCase().includes('date');
    let resolved = format;
    if (preferences?.date_format === 'iso') {
      resolved = dateOnly ? 'yyyy-MM-dd' : 'yyyy-MM-dd HH:mm';
    } else if (preferences?.date_format === 'short') {
      resolved = dateOnly ? 'shortDate' : 'short';
    }
    return this.datePipe.transform(value, resolved, timezone);
  }
}
