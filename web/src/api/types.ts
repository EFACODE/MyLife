export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  user_id: string;
  email: string;
  display_name: string;
  status: string;
  household_id: string | null;
  created_at: string;
}

/** A Life Event as returned by the timeline API (payload shape varies by type). */
export interface TimelineEvent {
  event_id: string;
  user_id: string;
  event_type: string;
  occurred_at: string;
  recorded_at: string;
  schema_version: number;
  source: string;
  correlation_id: string;
  raw_record_id: string | null;
  corrects_event_id: string | null;
  payload: Record<string, unknown>;
}

export interface TimelinePage {
  items: TimelineEvent[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface BriefingLine {
  kind: string;
  summary: string;
  evidence: string[];
}

export interface Briefing {
  user_id: string;
  generated_at: string;
  window_hours: number;
  event_count: number;
  lines: BriefingLine[];
}

export interface TimelineQuery {
  eventType?: string;
  limit?: number;
  offset?: number;
}

// --- Privacy & governance (T10.2) ---

export interface Consent {
  scope: string;
  granted: boolean;
  updated_at: string;
}

export interface AuditEntry {
  audit_id: string;
  action: string;
  actor_user_id: string | null;
  subject_user_id: string | null;
  resource: string | null;
  correlation_id: string;
  occurred_at: string;
  recorded_at: string;
}

export interface ErasureResult {
  deleted: Record<string, number>;
}

export interface ExportBundle {
  user: User;
  consents: Consent[];
  audit: AuditEntry[];
  events: unknown[];
  raw_records: unknown[];
  entities: unknown[];
  relationships: unknown[];
  accounts: unknown[];
  goals: unknown[];
  documents: unknown[];
}
