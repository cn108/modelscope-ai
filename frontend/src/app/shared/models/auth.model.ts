export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, string[]> | null;
  };
}
