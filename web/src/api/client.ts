import type {
  Account,
  AlertEmail,
  AlertPhone,
  Answer,
  AuditEntry,
  Balance,
  BankImportResult,
  Bill,
  BillOccurrence,
  BillPayment,
  Briefing,
  Calibration,
  Category,
  Forecast,
  Insight,
  InsightInput,
  Outcome,
  CaptureEventInput,
  CashFlow,
  Consent,
  ErasureResult,
  ConsolidationResult,
  CreateGoalInput,
  Document,
  DocumentText,
  EntityRecord,
  ExpenseInput,
  ExportBundle,
  ExtractedText,
  Goal,
  GoalProgress,
  HealthImportResult,
  LoginResponse,
  Memory,
  Milestone,
  NotificationOutcome,
  NotificationPreference,
  RelationshipRecord,
  SearchHit,
  NetWorth,
  PositionInput,
  RegisterBillInput,
  SetNotificationPreferenceInput,
  SleepInput,
  UpdateBillInput,
  UpdateTransactionInput,
  UpdateUserInput,
  SleepSession,
  TimelineEvent,
  TimelinePage,
  TimelineQuery,
  Transaction,
  TransactionInput,
  User,
  Workout,
  WorkoutInput,
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

  /** Register a new user (public — no auth token required or sent). */
  registerUser(input: { email: string; display_name: string; password: string }): Promise<User> {
    return this.request<User>("/users", { method: "POST", body: input, auth: false });
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

  /** Edit the signed-in user's editable profile fields (email is immutable). */
  updateCurrentUser(input: UpdateUserInput): Promise<User> {
    return this.request<User>("/users/me", { method: "PATCH", body: input });
  }

  /** A page of the user's timeline events, optionally filtered by type. */
  getTimeline(userId: string, query: TimelineQuery = {}): Promise<TimelinePage> {
    const params = new URLSearchParams({ user_id: userId });
    if (query.eventType) params.set("event_type", query.eventType);
    if (query.limit !== undefined) params.set("limit", String(query.limit));
    if (query.offset !== undefined) params.set("offset", String(query.offset));
    return this.request<TimelinePage>(`/timeline/events?${params.toString()}`);
  }

  /** Record a Life Event by hand. */
  captureEvent(input: CaptureEventInput): Promise<TimelineEvent> {
    return this.request<TimelineEvent>("/timeline/events", { method: "POST", body: input });
  }

  /** Deliver a rule-based, evidence-linked briefing for the user. */
  deliverBriefing(userId: string, windowHours = 24): Promise<Briefing> {
    return this.request<Briefing>("/briefing", {
      method: "POST",
      body: { user_id: userId, window_hours: windowHours },
    });
  }

  // --- Privacy & governance (T10.2) ---

  listConsents(): Promise<Consent[]> {
    return this.request<Consent[]>("/consents");
  }

  grantConsent(scope: string): Promise<Consent> {
    return this.request<Consent>("/consents", { method: "POST", body: { scope } });
  }

  revokeConsent(scope: string): Promise<void> {
    return this.request<void>(`/consents/${encodeURIComponent(scope)}`, { method: "DELETE" });
  }

  getAudit(): Promise<AuditEntry[]> {
    return this.request<AuditEntry[]>("/audit");
  }

  exportMe(): Promise<ExportBundle> {
    return this.request<ExportBundle>("/me/export");
  }

  deleteMe(): Promise<ErasureResult> {
    return this.request<ErasureResult>("/me", { method: "DELETE" });
  }

  // --- Finance (T10.4) ---

  listAccounts(): Promise<Account[]> {
    return this.request<Account[]>("/accounts");
  }

  createAccount(name: string, currency: string): Promise<Account> {
    return this.request<Account>("/accounts", { method: "POST", body: { name, currency } });
  }

  listCategories(): Promise<Category[]> {
    return this.request<Category[]>("/finance/categories");
  }

  createCategory(name: string): Promise<Category> {
    return this.request<Category>("/finance/categories", { method: "POST", body: { name } });
  }

  deleteCategory(categoryId: string): Promise<void> {
    return this.request<void>(`/finance/categories/${categoryId}`, { method: "DELETE" });
  }

  recordExpense(input: ExpenseInput): Promise<Transaction> {
    return this.request<Transaction>("/finance/expenses", { method: "POST", body: input });
  }

  recordTransaction(input: TransactionInput): Promise<Transaction> {
    return this.request<Transaction>("/finance/transactions", { method: "POST", body: input });
  }

  listTransactions(accountId?: string, limit?: number): Promise<Transaction[]> {
    const params = new URLSearchParams();
    if (accountId) params.set("account_id", accountId);
    if (limit !== undefined) params.set("limit", String(limit));
    const query = params.toString();
    return this.request<Transaction[]>(`/finance/transactions${query ? `?${query}` : ""}`);
  }

  updateTransaction(
    transactionEventId: string,
    input: UpdateTransactionInput,
  ): Promise<Transaction> {
    return this.request<Transaction>(`/finance/transactions/${transactionEventId}`, {
      method: "PATCH",
      body: input,
    });
  }

  deleteTransaction(transactionEventId: string): Promise<void> {
    return this.request<void>(`/finance/transactions/${transactionEventId}`, {
      method: "DELETE",
    });
  }

  recordPosition(input: PositionInput): Promise<Balance> {
    return this.request<Balance>("/finance/positions", { method: "POST", body: input });
  }

  accountBalance(accountId: string): Promise<Balance> {
    return this.request<Balance>(`/finance/accounts/${accountId}/balance`);
  }

  netWorth(): Promise<NetWorth> {
    return this.request<NetWorth>("/finance/net-worth");
  }

  cashFlow(occurredFrom: string, occurredTo: string): Promise<CashFlow> {
    const params = new URLSearchParams({ occurred_from: occurredFrom, occurred_to: occurredTo });
    return this.request<CashFlow>(`/finance/cash-flow?${params.toString()}`);
  }

  importBank(accountId: string, csv: string): Promise<BankImportResult> {
    return this.request<BankImportResult>("/finance/connectors/bank/import", {
      method: "POST",
      body: { account_id: accountId, csv },
    });
  }

  // --- Bills (T4.7) ---

  listBills(accountId?: string): Promise<Bill[]> {
    const params = new URLSearchParams();
    if (accountId) params.set("account_id", accountId);
    const query = params.toString();
    return this.request<Bill[]>(`/finance/bills${query ? `?${query}` : ""}`);
  }

  registerBill(input: RegisterBillInput): Promise<Bill> {
    return this.request<Bill>("/finance/bills", { method: "POST", body: input });
  }

  updateBill(billId: string, input: UpdateBillInput): Promise<Bill> {
    return this.request<Bill>(`/finance/bills/${billId}`, { method: "PATCH", body: input });
  }

  cancelBill(billId: string): Promise<void> {
    return this.request<void>(`/finance/bills/${billId}`, { method: "DELETE" });
  }

  payBill(billId: string, dueAt: string, amountMinor?: number): Promise<BillPayment> {
    return this.request<BillPayment>(`/finance/bills/${billId}/pay`, {
      method: "POST",
      body: { due_at: dueAt, amount_minor: amountMinor },
    });
  }

  billsReport(
    dueFrom: string,
    dueTo: string,
    options: { accountId?: string; paid?: boolean; overdue?: boolean } = {},
  ): Promise<BillOccurrence[]> {
    const params = new URLSearchParams({ due_from: dueFrom, due_to: dueTo });
    if (options.accountId) params.set("account_id", options.accountId);
    if (options.paid !== undefined) params.set("paid", String(options.paid));
    if (options.overdue !== undefined) params.set("overdue", String(options.overdue));
    return this.request<BillOccurrence[]>(`/finance/bills/report?${params.toString()}`);
  }

  runBillAlerts(): Promise<NotificationOutcome[]> {
    return this.request<NotificationOutcome[]>("/finance/bills/alerts/run", { method: "POST" });
  }

  // --- Notifications (T4.8) ---

  getNotificationPreferences(): Promise<NotificationPreference> {
    return this.request<NotificationPreference>("/notifications/preferences");
  }

  setNotificationPreferences(
    input: SetNotificationPreferenceInput,
  ): Promise<NotificationPreference> {
    return this.request<NotificationPreference>("/notifications/preferences", {
      method: "PUT",
      body: input,
    });
  }

  listAlertEmails(): Promise<AlertEmail[]> {
    return this.request<AlertEmail[]>("/notifications/alert-emails");
  }

  addAlertEmail(email: string): Promise<AlertEmail> {
    return this.request<AlertEmail>("/notifications/alert-emails", {
      method: "POST",
      body: { email },
    });
  }

  deleteAlertEmail(alertEmailId: string): Promise<void> {
    return this.request<void>(`/notifications/alert-emails/${alertEmailId}`, {
      method: "DELETE",
    });
  }

  listAlertPhones(): Promise<AlertPhone[]> {
    return this.request<AlertPhone[]>("/notifications/alert-phones");
  }

  addAlertPhone(phone: string): Promise<AlertPhone> {
    return this.request<AlertPhone>("/notifications/alert-phones", {
      method: "POST",
      body: { phone },
    });
  }

  deleteAlertPhone(alertPhoneId: string): Promise<void> {
    return this.request<void>(`/notifications/alert-phones/${alertPhoneId}`, {
      method: "DELETE",
    });
  }

  // --- Health (T10.5) ---

  listSleep(): Promise<SleepSession[]> {
    return this.request<SleepSession[]>("/health/sleep");
  }

  recordSleep(input: SleepInput): Promise<SleepSession> {
    return this.request<SleepSession>("/health/sleep", { method: "POST", body: input });
  }

  listWorkouts(): Promise<Workout[]> {
    return this.request<Workout[]>("/health/workouts");
  }

  recordWorkout(input: WorkoutInput): Promise<Workout> {
    return this.request<Workout>("/health/workouts", { method: "POST", body: input });
  }

  importHealth(csv: string): Promise<HealthImportResult> {
    return this.request<HealthImportResult>("/health/connectors/import", {
      method: "POST",
      body: { csv },
    });
  }

  // --- Goals (T10.6) ---

  listGoals(): Promise<Goal[]> {
    return this.request<Goal[]>("/goals");
  }

  createGoal(input: CreateGoalInput): Promise<Goal> {
    return this.request<Goal>("/goals", { method: "POST", body: input });
  }

  goalProgressAll(): Promise<GoalProgress[]> {
    return this.request<GoalProgress[]>("/goals/progress");
  }

  recordMilestone(goalId: string, value: number, note?: string | null): Promise<Milestone> {
    return this.request<Milestone>(`/goals/${goalId}/milestones`, {
      method: "POST",
      body: { value, note: note ?? null },
    });
  }

  listMilestones(goalId: string): Promise<Milestone[]> {
    return this.request<Milestone[]>(`/goals/${goalId}/milestones`);
  }

  // --- Knowledge (T10.7) ---

  uploadDocument(file: File): Promise<Document> {
    return this.upload<Document>("/documents", file);
  }

  listDocuments(): Promise<Document[]> {
    return this.request<Document[]>("/documents");
  }

  extractDocument(documentId: string): Promise<ExtractedText> {
    return this.request<ExtractedText>(`/documents/${documentId}/extract`, { method: "POST" });
  }

  getDocumentText(documentId: string): Promise<DocumentText> {
    return this.request<DocumentText>(`/documents/${documentId}/text`);
  }

  indexDocument(documentId: string): Promise<Memory> {
    return this.request<Memory>(`/documents/${documentId}/index`, { method: "POST" });
  }

  memorySearch(query: string, limit?: number): Promise<SearchHit[]> {
    const params = new URLSearchParams({ q: query });
    if (limit !== undefined) params.set("limit", String(limit));
    return this.request<SearchHit[]>(`/memory/search?${params.toString()}`);
  }

  consolidateGraph(): Promise<ConsolidationResult> {
    return this.request<ConsolidationResult>("/knowledge-graph/consolidate", { method: "POST" });
  }

  listEntities(): Promise<EntityRecord[]> {
    return this.request<EntityRecord[]>("/knowledge-graph/entities");
  }

  listRelationships(): Promise<RelationshipRecord[]> {
    return this.request<RelationshipRecord[]>("/knowledge-graph/relationships");
  }

  // --- Assistant (T10.8) ---

  assistantQuery(question: string): Promise<Answer> {
    return this.request<Answer>("/assistant/query", { method: "POST", body: { question } });
  }

  runAlerts(): Promise<Insight[]> {
    return this.request<Insight[]>("/assistant/alerts/run", { method: "POST" });
  }

  listInsights(): Promise<Insight[]> {
    return this.request<Insight[]>("/insights");
  }

  recordInsight(input: InsightInput): Promise<Insight> {
    return this.request<Insight>("/insights", { method: "POST", body: input });
  }

  // --- Forecast (T10.9) ---

  listForecasts(): Promise<Forecast[]> {
    return this.request<Forecast[]>("/forecasts");
  }

  runForecasts(horizonDays = 30): Promise<Forecast[]> {
    return this.request<Forecast[]>("/forecasts/run", {
      method: "POST",
      body: { horizon_days: horizonDays },
    });
  }

  simulateForecast(forecastId: string, scale: number, label?: string): Promise<Forecast> {
    return this.request<Forecast>(`/forecasts/${forecastId}/simulate`, {
      method: "POST",
      body: { scale, label: label ?? null },
    });
  }

  recordOutcome(
    forecastId: string,
    observedValue: number,
    observedAt: string,
    note?: string | null,
  ): Promise<Outcome> {
    return this.request<Outcome>(`/forecasts/${forecastId}/outcome`, {
      method: "POST",
      body: { observed_value: observedValue, observed_at: observedAt, note: note ?? null },
    });
  }

  calibration(): Promise<Calibration> {
    return this.request<Calibration>("/forecasts/calibration");
  }
}

/** API base URL from the build env (empty string → same origin). */
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "";
