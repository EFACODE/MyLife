import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import type { Account, BillRecurrence, Transaction } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { CategoryAvatar } from "../../components/ui/CategoryAvatar";
import { CategoryBadge } from "../../components/ui/CategoryBadge";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { Select } from "../../components/ui/Select";
import { StatCard } from "../../components/ui/StatCard";
import { Tabs, type TabItem } from "../../components/ui/Tabs";
import { categorySolidClass } from "../../lib/categoryColor";
import { money, moneyByCurrency, shortDate } from "../../lib/format";
import { useAsync, type AsyncResult } from "../../lib/useAsync";

type FinanceApi = Pick<
  ApiClient,
  | "listAccounts"
  | "createAccount"
  | "recordExpense"
  | "recordTransaction"
  | "listTransactions"
  | "netWorth"
  | "cashFlow"
  | "importBank"
  | "listBills"
  | "registerBill"
  | "cancelBill"
  | "payBill"
  | "billsReport"
  | "runBillAlerts"
  | "getNotificationPreferences"
  | "setNotificationPreferences"
>;

const TABS: TabItem[] = [
  { id: "overview", label: "Visão geral" },
  { id: "transactions", label: "Transações" },
  { id: "bills", label: "Contas a pagar" },
  { id: "categories", label: "Categorias" },
];

export function FinancePage() {
  const client = useApiClient();
  const [tab, setTab] = useState(TABS[0].id);
  const accounts = useAsync(() => client.listAccounts(), [client]);
  const transactions = useAsync(() => client.listTransactions(undefined, 200), [client]);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">Finanças</h1>
      <p className="mb-6 text-sm text-gray-500">
        Contas, transações, contas a pagar e categorias.
      </p>
      <Tabs items={TABS} active={tab} onChange={setTab} />
      {tab === "overview" && <OverviewTab client={client} accounts={accounts} />}
      {tab === "transactions" && (
        <TransactionsTab
          client={client}
          accounts={accounts.data ?? []}
          transactions={transactions}
        />
      )}
      {tab === "bills" && <BillsTab client={client} />}
      {tab === "categories" && <CategoriesTab transactions={transactions.data ?? []} />}
    </div>
  );
}

// --- Visão geral ---------------------------------------------------------

function OverviewTab({
  client,
  accounts,
}: {
  client: FinanceApi;
  accounts: AsyncResult<Account[]>;
}) {
  return (
    <>
      <Accounts client={client} accounts={accounts} />
      <NetWorthView client={client} />
      <CashFlowView client={client} />
      <BankImport client={client} />
    </>
  );
}

function Accounts({
  client,
  accounts,
}: {
  client: FinanceApi;
  accounts: AsyncResult<Account[]>;
}) {
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [error, setError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.createAccount(name.trim(), currency.trim().toUpperCase());
      setName("");
      await accounts.run();
    } catch {
      setError("Could not create the account.");
    }
  }

  return (
    <Section title="Accounts">
      <form onSubmit={create} className="mb-4 flex items-end gap-2">
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Currency">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Button type="submit">Open account</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {accounts.status === "error" && <ErrorText>Could not load accounts.</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(accounts.data ?? []).map((account) => (
          <li key={account.account_id} className="rounded border border-gray-200 px-3 py-2">
            <span className="font-medium">{account.name}</span>
            <span className="text-gray-500"> · {account.currency}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function NetWorthView({ client }: { client: FinanceApi }) {
  const netWorth = useAsync(() => client.netWorth(), [client]);
  return (
    <Section title="Net worth" actions={<Button onClick={() => netWorth.run()}>Refresh</Button>}>
      {netWorth.status === "error" && <ErrorText>Could not load net worth.</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(netWorth.data?.currencies ?? []).map((total) => (
          <li key={total.currency}>
            <span className="font-medium">{money(total.total_minor, total.currency)}</span>
          </li>
        ))}
        {netWorth.status === "ready" && netWorth.data?.currencies.length === 0 && (
          <li className="text-gray-500">No balances yet.</li>
        )}
      </ul>
    </Section>
  );
}

function CashFlowView({ client }: { client: FinanceApi }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const flow = useAsync(
    () => client.cashFlow(new Date(from).toISOString(), new Date(to).toISOString()),
    [client, from, to],
    { immediate: false },
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    void flow.run();
  }

  return (
    <Section title="Cash flow">
      <form onSubmit={submit} className="mb-3 flex items-end gap-2">
        <Field label="From">
          <TextInput
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required
          />
        </Field>
        <Field label="To">
          <TextInput
            type="datetime-local"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            required
          />
        </Field>
        <Button type="submit">Compute</Button>
      </form>
      {flow.status === "error" && <ErrorText>Could not compute cash flow.</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(flow.data?.flows ?? []).map((currencyFlow) => (
          <li key={currencyFlow.currency}>
            <span className="font-medium">{currencyFlow.currency}</span>: in{" "}
            {money(currencyFlow.inflow_minor, currencyFlow.currency)}, out{" "}
            {money(currencyFlow.outflow_minor, currencyFlow.currency)}, net{" "}
            {money(currencyFlow.net_minor, currencyFlow.currency)}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function BankImport({ client }: { client: FinanceApi }) {
  const [accountId, setAccountId] = useState("");
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    try {
      const outcome = await client.importBank(accountId.trim(), csv);
      setResult(`Imported ${outcome.events_created} (skipped ${outcome.skipped_duplicates}).`);
    } catch (caught) {
      const status = (caught as { status?: number }).status;
      setError(
        status === 403
          ? "Grant the 'bank' consent first (Consent page)."
          : "Could not import the CSV.",
      );
    }
  }

  return (
    <Section title="Bank CSV import">
      <form onSubmit={submit} className="flex flex-col gap-2">
        <Field label="Account id">
          <TextInput value={accountId} onChange={(e) => setAccountId(e.target.value)} required />
        </Field>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-gray-700">CSV</span>
          <textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            rows={4}
            className="rounded border border-gray-300 px-2 py-1 font-mono text-xs"
            required
          />
        </label>
        <div>
          <Button type="submit">Import</Button>
        </div>
      </form>
      {result && <p className="mt-2 text-sm text-green-700">{result}</p>}
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

// --- Transações ------------------------------------------------------------

type TxKindFilter = "all" | "expense" | "import";

function TransactionsTab({
  client,
  accounts,
  transactions,
}: {
  client: FinanceApi;
  accounts: Account[];
  transactions: AsyncResult<Transaction[]>;
}) {
  const [accountFilter, setAccountFilter] = useState("");
  const [kindFilter, setKindFilter] = useState<TxKindFilter>("all");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);

  const accountName = useMemo(() => {
    const byId = new Map(accounts.map((a) => [a.account_id, a.name]));
    return (id: string) => byId.get(id) ?? id.slice(0, 8);
  }, [accounts]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (transactions.data ?? []).filter((t) => {
      if (accountFilter && t.account_id !== accountFilter) return false;
      if (kindFilter !== "all" && t.kind !== kindFilter) return false;
      if (needle) {
        const haystack = `${t.description} ${t.category ?? ""}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [transactions.data, accountFilter, kindFilter, search]);

  const totals = useMemo(() => {
    const expenses = filtered.filter((t) => t.amount_minor < 0);
    const income = filtered.filter((t) => t.amount_minor >= 0);
    return {
      count: filtered.length,
      expenses: moneyByCurrency(expenses),
      income: moneyByCurrency(income),
      balance: moneyByCurrency(filtered),
    };
  }, [filtered]);

  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <StatCard label="Total de transações" value={String(totals.count)} />
        <StatCard label="Despesas" value={totals.expenses} tone="critical" />
        <StatCard label="Receitas" value={totals.income} tone="good" />
        <StatCard label="Saldo" value={totals.balance} />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          type="search"
          aria-label="Buscar transações"
          placeholder="Buscar transações..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="min-w-[220px] flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        <Select
          aria-label="Filtrar por conta"
          value={accountFilter}
          onChange={(e) => setAccountFilter(e.target.value)}
        >
          <option value="">Todas as contas</option>
          {accounts.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filtrar por tipo"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value as TxKindFilter)}
        >
          <option value="all">Todos os tipos</option>
          <option value="expense">Despesas manuais</option>
          <option value="import">Importadas</option>
        </Select>
        <Button onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancelar" : "+ Nova Transação"}
        </Button>
      </div>

      {showForm && (
        <NewTransactionForm
          client={client}
          accounts={accounts}
          onCreated={() => {
            setShowForm(false);
            void transactions.run();
          }}
        />
      )}

      {transactions.status === "error" && <ErrorText>Could not load transactions.</ErrorText>}
      <TransactionsTable
        transactions={filtered}
        accountName={accountName}
        loading={transactions.status === "loading"}
      />
    </div>
  );
}

function NewTransactionForm({
  client,
  accounts,
  onCreated,
}: {
  client: FinanceApi;
  accounts: Account[];
  onCreated: () => void;
}) {
  const [accountId, setAccountId] = useState("");
  const [kind, setKind] = useState<"expense" | "income">("expense");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId && accounts.length > 0) setAccountId(accounts[0].account_id);
  }, [accounts, accountId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const input = {
        account_id: accountId,
        amount_minor: Number(amount),
        currency: currency.trim().toUpperCase(),
        description: description.trim(),
        category: category.trim() || null,
      };
      if (kind === "expense") {
        await client.recordExpense(input);
      } else {
        await client.recordTransaction(input);
      }
      onCreated();
    } catch {
      setError("Could not record the transaction.");
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Account">
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
            <option value="" disabled>
              Select an account
            </option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Type">
          <Select value={kind} onChange={(e) => setKind(e.target.value as "expense" | "income")}>
            <option value="expense">Despesa</option>
            <option value="income">Receita</option>
          </Select>
        </Field>
        <Field label="Amount (minor units)">
          <TextInput
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </Field>
        <Field label="Currency">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Field label="Description">
          <TextInput
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </Field>
        <Field label="Category">
          <TextInput value={category} onChange={(e) => setCategory(e.target.value)} />
        </Field>
        <Button type="submit">Save</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

function TransactionsTable({
  transactions,
  accountName,
  loading,
}: {
  transactions: Transaction[];
  accountName: (id: string) => string;
  loading: boolean;
}) {
  if (loading && transactions.length === 0) {
    return <p className="text-sm text-gray-500">Loading…</p>;
  }
  if (transactions.length === 0) {
    return <p className="text-sm text-gray-500">No transactions found.</p>;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-4 py-2 font-medium">Descrição</th>
            <th className="px-4 py-2 font-medium">Categoria</th>
            <th className="px-4 py-2 font-medium">Conta</th>
            <th className="px-4 py-2 font-medium">Data</th>
            <th className="px-4 py-2 text-right font-medium">Valor</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {transactions.map((t) => (
            <tr key={t.event_id} className="hover:bg-gray-50">
              <td className="px-4 py-2.5">
                <div className="flex items-center gap-3">
                  <CategoryAvatar label={t.description} category={t.category} />
                  <span className="font-medium text-gray-900">{t.description}</span>
                </div>
              </td>
              <td className="px-4 py-2.5">
                <CategoryBadge category={t.category} />
              </td>
              <td className="px-4 py-2.5 text-gray-500">{accountName(t.account_id)}</td>
              <td className="px-4 py-2.5 text-gray-500">{shortDate(t.occurred_at)}</td>
              <td
                className={
                  "px-4 py-2.5 text-right font-medium " +
                  (t.amount_minor < 0 ? "text-red-600" : "text-green-700")
                }
              >
                {money(t.amount_minor, t.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Categorias --------------------------------------------------------

function CategoriesTab({ transactions }: { transactions: Transaction[] }) {
  const rows = useMemo(() => {
    const byCategory = new Map<string, { total: Map<string, number>; count: number }>();
    for (const t of transactions) {
      const key = t.category ?? "Sem categoria";
      const entry = byCategory.get(key) ?? { total: new Map<string, number>(), count: 0 };
      entry.total.set(t.currency, (entry.total.get(t.currency) ?? 0) + Math.abs(t.amount_minor));
      entry.count += 1;
      byCategory.set(key, entry);
    }
    return [...byCategory.entries()]
      .map(([category, { total, count }]) => ({
        category,
        count,
        formatted: [...total.entries()].map(([c, v]) => money(v, c)).join(" · "),
        magnitude: [...total.values()].reduce((a, b) => a + b, 0),
      }))
      .sort((a, b) => b.magnitude - a.magnitude);
  }, [transactions]);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        No transactions yet — categories will appear here once you record some.
      </p>
    );
  }

  const max = Math.max(...rows.map((r) => r.magnitude), 1);

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <div key={row.category} className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 flex items-center justify-between">
            <CategoryBadge category={row.category === "Sem categoria" ? null : row.category} />
            <span className="text-sm font-medium text-gray-900">{row.formatted}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-gray-100">
            <div
              className={
                "h-1.5 rounded-full " +
                (row.category === "Sem categoria"
                  ? "bg-gray-300"
                  : categorySolidClass(row.category))
              }
              style={{ width: `${(row.magnitude / max) * 100}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-gray-400">{row.count} transação(ões)</div>
        </div>
      ))}
    </div>
  );
}

// --- Contas a pagar ------------------------------------------------------

function BillsTab({ client }: { client: FinanceApi }) {
  return (
    <>
      <Bills client={client} />
      <PayBill client={client} />
      <BillsReport client={client} />
      <NotificationPreferences client={client} />
    </>
  );
}

function Bills({ client }: { client: FinanceApi }) {
  const bills = useAsync(() => client.listBills(), [client]);
  const [accountId, setAccountId] = useState("");
  const [payee, setPayee] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [category, setCategory] = useState("");
  const [recurrence, setRecurrence] = useState<BillRecurrence>("monthly");
  const [dueDay, setDueDay] = useState("5");
  const [dueAt, setDueAt] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function register(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.registerBill({
        account_id: accountId.trim(),
        payee: payee.trim(),
        amount_minor: Number(amount),
        currency: currency.trim().toUpperCase(),
        category: category.trim() || null,
        recurrence,
        due_day: recurrence === "monthly" ? Number(dueDay) : null,
        due_at: recurrence === "once" && dueAt ? new Date(dueAt).toISOString() : null,
      });
      setPayee("");
      setAmount("");
      await bills.run();
    } catch {
      setError("Could not register the bill.");
    }
  }

  async function cancel(billId: string) {
    await client.cancelBill(billId);
    await bills.run();
  }

  return (
    <Section title="Bills (contas a pagar)">
      <form onSubmit={register} className="mb-4 flex flex-wrap items-end gap-2">
        <Field label="Account id">
          <TextInput value={accountId} onChange={(e) => setAccountId(e.target.value)} required />
        </Field>
        <Field label="Payee">
          <TextInput value={payee} onChange={(e) => setPayee(e.target.value)} required />
        </Field>
        <Field label="Amount (minor units)">
          <TextInput
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </Field>
        <Field label="Currency">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Field label="Category">
          <TextInput value={category} onChange={(e) => setCategory(e.target.value)} />
        </Field>
        <Field label="Recurrence">
          <Select
            value={recurrence}
            onChange={(e) => setRecurrence(e.target.value as BillRecurrence)}
          >
            <option value="monthly">Monthly</option>
            <option value="once">Once</option>
          </Select>
        </Field>
        {recurrence === "monthly" ? (
          <Field label="Due day">
            <TextInput
              type="number"
              min={1}
              max={31}
              value={dueDay}
              onChange={(e) => setDueDay(e.target.value)}
              required
            />
          </Field>
        ) : (
          <Field label="Due date">
            <TextInput
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              required
            />
          </Field>
        )}
        <Button type="submit">Register bill</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {bills.status === "error" && <ErrorText>Could not load bills.</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(bills.data ?? []).map((bill) => (
          <li
            key={bill.bill_id}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
          >
            <span className="flex items-center gap-2">
              <span className="font-medium">{bill.payee}</span>
              <span className="text-gray-500">
                · {money(bill.amount_minor, bill.currency)} ·{" "}
                {bill.recurrence === "monthly" ? `day ${bill.due_day}` : bill.due_at}
                {!bill.active && " · cancelled"}
              </span>
              {bill.category && <CategoryBadge category={bill.category} />}
            </span>
            {bill.active && (
              <button
                type="button"
                onClick={() => void cancel(bill.bill_id)}
                className="rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Cancel
              </button>
            )}
          </li>
        ))}
        {bills.status === "ready" && (bills.data ?? []).length === 0 && (
          <li className="text-gray-500">No bills yet.</li>
        )}
      </ul>
    </Section>
  );
}

function PayBill({ client }: { client: FinanceApi }) {
  const [billId, setBillId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [amount, setAmount] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.payBill(
        billId.trim(),
        new Date(dueAt).toISOString(),
        amount.trim() ? Number(amount) : undefined,
      );
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  return (
    <Section title="Pay a bill">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Bill id">
          <TextInput value={billId} onChange={(e) => setBillId(e.target.value)} required />
        </Field>
        <Field label="Due date (occurrence)">
          <TextInput
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            required
          />
        </Field>
        <Field label="Amount (minor units, optional)">
          <TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Button type="submit">Mark as paid</Button>
      </form>
      {status === "ok" && <p className="mt-2 text-sm text-green-700">Paid.</p>}
      {status === "error" && <ErrorText>Could not record the payment.</ErrorText>}
    </Section>
  );
}

function BillsReport({ client }: { client: FinanceApi }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [paid, setPaid] = useState<"" | "true" | "false">("");
  const [overdue, setOverdue] = useState<"" | "true" | "false">("");
  const report = useAsync(
    () =>
      client.billsReport(new Date(from).toISOString(), new Date(to).toISOString(), {
        paid: paid === "" ? undefined : paid === "true",
        overdue: overdue === "" ? undefined : overdue === "true",
      }),
    [client, from, to, paid, overdue],
    { immediate: false },
  );
  const [alertStatus, setAlertStatus] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    void report.run();
  }

  async function runAlerts() {
    setAlertStatus(null);
    try {
      const outcomes = await client.runBillAlerts();
      const sent = outcomes.filter((outcome) => outcome.delivered).length;
      setAlertStatus(`${sent}/${outcomes.length} reminder(s) delivered.`);
    } catch {
      setAlertStatus("Could not run the alert scan.");
    }
  }

  return (
    <Section
      title="Bills report"
      actions={<Button onClick={() => void runAlerts()}>Run alerts now</Button>}
    >
      <form onSubmit={submit} className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Due from">
          <TextInput
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required
          />
        </Field>
        <Field label="Due to">
          <TextInput
            type="datetime-local"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            required
          />
        </Field>
        <Field label="Paid">
          <Select value={paid} onChange={(e) => setPaid(e.target.value as typeof paid)}>
            <option value="">Any</option>
            <option value="true">Paid</option>
            <option value="false">Unpaid</option>
          </Select>
        </Field>
        <Field label="Overdue">
          <Select value={overdue} onChange={(e) => setOverdue(e.target.value as typeof overdue)}>
            <option value="">Any</option>
            <option value="true">Overdue</option>
            <option value="false">Not overdue</option>
          </Select>
        </Field>
        <Button type="submit">Filter</Button>
      </form>
      {alertStatus && <p className="mb-2 text-sm text-gray-700">{alertStatus}</p>}
      {report.status === "error" && <ErrorText>Could not load the report.</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(report.data ?? []).map((occurrence) => (
          <li
            key={`${occurrence.bill_id}-${occurrence.period}`}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
          >
            <span className="flex items-center gap-2">
              <span className="font-medium">{occurrence.payee}</span>
              <span className="text-gray-500">
                · {money(occurrence.amount_minor, occurrence.currency)} · due{" "}
                {occurrence.due_at}
              </span>
              {occurrence.category && <CategoryBadge category={occurrence.category} />}
            </span>
            <span
              className={
                occurrence.paid
                  ? "text-green-700"
                  : occurrence.overdue
                    ? "text-red-600"
                    : "text-gray-500"
              }
            >
              {occurrence.paid ? "Paid" : occurrence.overdue ? "Overdue" : "Unpaid"}
            </span>
          </li>
        ))}
        {report.status === "ready" && (report.data ?? []).length === 0 && (
          <li className="text-gray-500">No occurrences in range.</li>
        )}
      </ul>
    </Section>
  );
}

function NotificationPreferences({ client }: { client: FinanceApi }) {
  const preference = useAsync(() => client.getNotificationPreferences(), [client]);
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [whatsappPhone, setWhatsappPhone] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  useEffect(() => {
    if (preference.data) {
      setEmailEnabled(preference.data.email_enabled);
      setWhatsappEnabled(preference.data.whatsapp_enabled);
      setWhatsappPhone(preference.data.whatsapp_phone ?? "");
    }
  }, [preference.data]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.setNotificationPreferences({
        email_enabled: emailEnabled,
        whatsapp_enabled: whatsappEnabled,
        whatsapp_phone: whatsappPhone.trim() || null,
      });
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  return (
    <Section title="Reminder preferences">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={emailEnabled}
            onChange={(e) => setEmailEnabled(e.target.checked)}
          />
          Email
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={whatsappEnabled}
            onChange={(e) => setWhatsappEnabled(e.target.checked)}
          />
          WhatsApp
        </label>
        <Field label="WhatsApp number">
          <TextInput
            value={whatsappPhone}
            onChange={(e) => setWhatsappPhone(e.target.value)}
            placeholder="+5511999999999"
          />
        </Field>
        <Button type="submit">Save</Button>
      </form>
      {status === "ok" && <p className="mt-2 text-sm text-green-700">Saved.</p>}
      {status === "error" && <ErrorText>Could not save preferences.</ErrorText>}
    </Section>
  );
}
