import { AuthResponse, User } from '../../shared/models/auth.model';

export const ACCESS_TOKEN_KEY = 'msa.access';
export const REFRESH_TOKEN_KEY = 'msa.refresh';
export const USER_KEY = 'msa.user';

function storage(): Storage | null {
  return typeof localStorage === 'undefined' ? null : localStorage;
}

export function readAccessToken(): string | null {
  return storage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
}

export function readRefreshToken(): string | null {
  return storage()?.getItem(REFRESH_TOKEN_KEY) ?? null;
}

export function readStoredUser(): User | null {
  const raw = storage()?.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function persistSession(response: AuthResponse): void {
  const store = storage();
  if (!store) {
    return;
  }
  store.setItem(ACCESS_TOKEN_KEY, response.tokens.access);
  store.setItem(REFRESH_TOKEN_KEY, response.tokens.refresh);
  store.setItem(USER_KEY, JSON.stringify(response.user));
}

export function persistUser(user: User): void {
  storage()?.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  const store = storage();
  if (!store) {
    return;
  }
  store.removeItem(ACCESS_TOKEN_KEY);
  store.removeItem(REFRESH_TOKEN_KEY);
  store.removeItem(USER_KEY);
}
