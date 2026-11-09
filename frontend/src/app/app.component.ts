import { Component, OnInit, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AuthService } from './core/authentication/auth.service';

@Component({
  selector: 'msa-root',
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class AppComponent implements OnInit {
  private readonly auth = inject(AuthService);

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.me().subscribe({ error: () => this.auth.logout() });
    }
  }
}
