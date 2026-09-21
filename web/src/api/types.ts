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

// --- Forecast (T10.9) ---

export interface Assumption {
  name: string;
  value: string;
  basis: string;
}

export interface ForecastPoint {
  at: string;
  value: number;
  lower: number;
  upper: number;
}

export interface Forecast {
  forecast_id: string;
  metric: string;
  unit: string;
  horizon_days: number;
  points: ForecastPoint[];
  assumptions: Assumption[];
  confidence: number;
  limitations: string;
  method: string;
  evidence: string[];
  generated_at: string;
}

export interface Outcome {
  outcome_id: string;
  forecast_id: string;
  observed_value: number;
  observed_at: string;
  note: string | null;
  recorded_at: string;
}

export interface CalibrationRecord {
  forecast_id: string;
  metric: string;
  observed_value: number;
  predicted_value: number;
  error: number;
  within_interval: boolean;
  observed_at: string;
}

export interface Calibration {
  total: number;
  within_interval: number;
  hit_rate: number;
  mean_abs_error: number;
  records: CalibrationRecord[];
}

// --- Assistant (T10.8) ---

export interface Insight {
  insight_id: string;
  claim: string;
  rationale: string;
  confidence: number;
  limitations: string;
  next_safe_action: string | null;
  generator: string;
  evidence: string[];
  generated_at: string;
}

export interface Answer {
  grounded: boolean;
  answer: string;
  insight: Insight | null;
  tools_used: string[];
  evidence_count: number;
}

export interface InsightInput {
  claim: string;
  rationale: string;
  evidence: string[];
  confidence: number;
  limitations: string;
  next_safe_action?: string | null;
}

// --- Knowledge (T10.7) ---

export interface Document {
  document_id: string;
  filename: string;
  content_type: string;
  byte_size: number;
  checksum: string;
  created_at: string;
}

export interface ExtractedText {
  document_id: string;
  method: string;
  extractor_version: string;
  char_count: number;
}

export interface DocumentText {
  document_id: string;
  text: string;
}

export interface Memory {
  memory_id: string;
  document_id: string;
  embedder: string;
  dimension: number;
  indexed_at: string;
}

export interface SearchHit {
  document_id: string;
  score: number;
  preview: string;
}

export interface ConsolidationResult {
  entities: number;
  relationships: number;
}

export interface EntityRecord {
  entity_id: string;
  user_id: string;
  entity_type: string;
  entity_key: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrences: number;
}

export interface RelationshipRecord {
  relationship_id: string;
  user_id: string;
  source_entity_id: string;
  target_entity_id: string;
  rel_type: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrences: number;
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

// --- Bills (T4.7) ---

export type BillRecurrence = "monthly" | "once";

export interface Bill {
  bill_id: string;
  account_id: string;
  payee: string;
  amount_minor: number;
  currency: string;
  category: string | null;
  recurrence: BillRecurrence;
  due_day: number | null;
  due_at: string | null;
  active: boolean;
  created_at: string;
}

export interface RegisterBillInput {
  account_id: string;
  payee: string;
  amount_minor: number;
  currency: string;
  category?: string | null;
  recurrence: BillRecurrence;
  due_day?: number | null;
  due_at?: string | null;
}

export interface BillPayment {
  event_id: string;
  bill_id: string;
  period: string;
  due_at: string;
  amount_minor: number;
  paid_at: string;
  transaction_id: string | null;
}

export interface BillOccurrence {
  bill_id: string;
  account_id: string;
  payee: string;
  category: string | null;
  currency: string;
  amount_minor: number;
  period: string;
  due_at: string;
  paid: boolean;
  paid_at: string | null;
  overdue: boolean;
}

// --- Notifications (T4.8) ---

export type NotificationChannel = "email" | "whatsapp";

export interface NotificationPreference {
  email_enabled: boolean;
  whatsapp_enabled: boolean;
  whatsapp_phone: string | null;
  updated_at: string;
}

export interface SetNotificationPreferenceInput {
  email_enabled: boolean;
  whatsapp_enabled: boolean;
  whatsapp_phone?: string | null;
}

export interface NotificationOutcome {
  request_event_id: string;
  channel: NotificationChannel;
  recipient: string;
  delivered: boolean;
  provider_message_id: string | null;
  reason: string | null;
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
