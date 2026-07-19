export interface LoginResponse {
  access_token: string;
  token_type: string;
}

/** A Life Event as returned by the timeline API (payload shape varies by type). */
export interface TimelineEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  recorded_at: string;
  source: string;
  correlation_id: string;
  payload: Record<string, unknown>;
}

export interface TimelinePage {
  items: TimelineEvent[];
  next_cursor: string | null;
}

export interface BriefingLine {
  text: string;
  evidence: string[];
}

export interface Briefing {
  generated_at: string;
  lines: BriefingLine[];
}
