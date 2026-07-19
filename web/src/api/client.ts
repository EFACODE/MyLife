import type { LoginResponse } from "./types";

/** Raised when the API returns a non-2xx response. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Attach the bearer token (default true). */
  auth?: boolean;
}

/** A thin, typed wrapper over the My Life HTTP API. */
export class ApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getToken: () => string | null,
  ) {}

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, auth = true } = options;
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth) {
      const token = this.getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      throw new ApiError(response.status, `${method} ${path} -> ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  /** OAuth2 password flow: exchange credentials for an access token. */
  async login(email: string, password: string): Promise<string> {
    const form = new URLSearchParams({ username: email, password });
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
    if (!response.ok) throw new ApiError(response.status, "login failed");
    const data = (await response.json()) as LoginResponse;
    return data.access_token;
  }
}

/** API base URL from the build env (empty string → same origin). */
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "";
