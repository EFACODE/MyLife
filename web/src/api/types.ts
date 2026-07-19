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

// --- Goals (T10.6) ---

export interface Goal {
  goal_id: string;
  title: string;
  metric: string;
  target_value: number;
  unit: string;
  currency: string | null;
  due_at: string | null;
  created_at: string;
}

export interface Milestone {
  event_id: string;
  goal_id: string;
  value: number;
  note: string | null;
  occurred_at: string;
}

export interface GoalProgress {
  goal_id: string;
  metric: string;
  current_value: number;
  target_value: number;
  progress_ratio: number;
  achieved: boolean;
  source: string;
  evidence: string[];
}

export interface CreateGoalInput {
  title: string;
  metric: string;
  target_value: number;
  unit: string;
  currency?: string | null;
  due_at?: string | null;
}

// --- Health (T10.5) ---

export interface SleepSession {
  event_id: string;
  occurred_at: string;
  duration_minutes: number;
  quality: string | null;
}

export interface Workout {
  event_id: string;
  occurred_at: string;
  activity: string;
  duration_minutes: number;
  distance_meters: number | null;
  energy_kcal: number | null;
}

export interface HealthImportResult {
  source: string;
  raw_ingested: number;
  events_created: number;
  skipped_duplicates: number;
}

export interface SleepInput {
  occurred_at: string;
  duration_minutes: number;
  quality?: string | null;
}

export interface WorkoutInput {
  occurred_at: string;
  activity: string;
  duration_minutes: number;
  distance_meters?: number | null;
  energy_kcal?: number | null;
}

// --- Finance (T10.4) ---

export interface Account {
  account_id: string;
  name: string;
  currency: string;
  created_at: string;
}

export interface Transaction {
  event_id: string;
  kind: string;
  account_id: string;
  amount_minor: number;
  currency: string;
  description: string;
  category: string | null;
  occurred_at: string;
}

export interface Balance {
  account_id: string;
  currency: string;
  balance_minor: number;
  as_of: string | null;
}

export interface CurrencyTotal {
  currency: string;
  total_minor: number;
}

export interface CurrencyFlow {
  currency: string;
  inflow_minor: number;
  outflow_minor: number;
  net_minor: number;
}

export interface NetWorth {
  currencies: CurrencyTotal[];
  accounts: Balance[];
}

export interface CashFlow {
  occurred_from: string;
  occurred_to: string;
  flows: CurrencyFlow[];
}

export interface BankImportResult {
  source: string;
  raw_ingested: number;
  events_created: number;
  skipped_duplicates: number;
}

export interface ExpenseInput {
  account_id: string;
  amount_minor: number;
  currency: string;
  description: string;
  category?: string | null;
}

export interface TransactionInput extends ExpenseInput {
  external_id?: string | null;
}

export interface PositionInput {
  account_id: string;
  value_minor: number;
  currency: string;
}

// --- Timeline capture (T10.3) ---

export interface CaptureEventInput {
  user_id: string;
  occurred_at: string;
  title: string;
  category: string;
  note?: string | null;
  source?: string;
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
