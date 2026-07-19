import type {
  Briefing,
  LoginResponse,
  TimelinePage,
  TimelineQuery,
  User,
} from "./types";

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
    private readonly onUnauthorized?: () => void,
  ) {}

  private fail(status: number, message: string): never {
    if (status === 401) this.onUnauthorized?.();
    throw new ApiError(status, message);
  }

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
    if (!response.ok) this.fail(response.status, `${method} ${path} -> ${response.status}`);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  /** Upload a file as multipart/form-data (field name "file"). */
  async upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData();
    form.append("file", file);
    const headers: Record<string, string> = {};
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!response.ok) this.fail(response.status, `POST ${path} -> ${response.status}`);
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

  /** The signed-in user. */
  me(): Promise<User> {
    return this.request<User>("/auth/me");
  }

  /** A page of the user's timeline events, optionally filtered by type. */
  getTimeline(userId: string, query: TimelineQuery = {}): Promise<TimelinePage> {
    const params = new URLSearchParams({ user_id: userId });
    if (query.eventType) params.set("event_type", query.eventType);
    if (query.limit !== undefined) params.set("limit", String(query.limit));
    if (query.offset !== undefined) params.set("offset", String(query.offset));
    return this.request<TimelinePage>(`/timeline/events?${params.toString()}`);
  }

  /** Deliver a rule-based, evidence-linked briefing for the user. */
  deliverBriefing(userId: string, windowHours = 24): Promise<Briefing> {
    return this.request<Briefing>("/briefing", {
      method: "POST",
      body: { user_id: userId, window_hours: windowHours },
    });
  }
}

/** API base URL from the build env (empty string → same origin). */
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "";
