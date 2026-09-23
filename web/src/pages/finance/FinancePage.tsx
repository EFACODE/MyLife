import {
  AlertTriangle,
  Bell,
  Calculator,
  CalendarClock,
  CheckCircle2,
  Clock,
  ListChecks,
  PiggyBank,
  PlusCircle,
  Receipt,
  Scale,
  TrendingDown,
  TrendingUp,
  User as UserIcon,
  Wallet,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, type ApiClient } from "../../api/client";
import type {
  Account,
  AlertEmail,
  AlertPhone,
  Balance,
  Bill,
  BillRecurrence,
  Category,
  ExpenseType,
  Transaction,
} from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { CategoryAvatar } from "../../components/ui/CategoryAvatar";
import { CategoryBadge } from "../../components/ui/CategoryBadge";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { Select } from "../../components/ui/Select";
import { StatCard } from "../../components/ui/StatCard";
import { SubTabs, type SubTabItem } from "../../components/ui/SubTabs";
import { Tabs, type TabItem } from "../../components/ui/Tabs";
import { categorySolidClass } from "../../lib/categoryColor";
import { money, moneyByCurrency, moneySuffixed, parseMoneyInput, shortDate } from "../../lib/format";
import { useAsync, type AsyncResult } from "../../lib/useAsync";

type FinanceApi = Pick<
  ApiClient,
  | "listAccounts"
  | "createAccount"
  | "listCategories"
  | "createCategory"
  | "deleteCategory"
  | "recordExpense"
  | "recordTransaction"
  | "listTransactions"
  | "updateTransaction"
  | "deleteTransaction"
  | "netWorth"
  | "importBank"
  | "listBills"
  | "registerBill"
  | "updateBill"
  | "cancelBill"
  | "payBill"
  | "billsReport"
  | "runBillAlerts"
  | "getNotificationPreferences"
  | "setNotificationPreferences"
  | "listAlertEmails"
  | "addAlertEmail"
  | "deleteAlertEmail"
  | "listAlertPhones"
  | "addAlertPhone"
  | "deleteAlertPhone"
  | "me"
  | "updateCurrentUser"
>;

const TABS: TabItem[] = [
  { id: "overview", label: "Visão geral" },
  { id: "transactions", label: "Transações" },
  { id: "bills", label: "Contas a pagar" },
  { id: "categories", label: "Categorias" },
  { id: "settings", label: "Configurações" },
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
      {tab === "overview" && (
        <OverviewTab
          client={client}
          accounts={accounts.data ?? []}
          transactions={transactions.data ?? []}
        />
      )}
      {tab === "transactions" && (
        <TransactionsTab
          client={client}
          accounts={accounts.data ?? []}
          transactions={transactions}
        />
      )}
      {tab === "bills" && <BillsTab client={client} accounts={accounts.data ?? []} />}
      {tab === "categories" && <CategoriesTab client={client} />}
      {tab === "settings" && <SettingsTab client={client} accounts={accounts} />}
    </div>
  );
}

// --- Visão geral ---------------------------------------------------------

function OverviewTab({
  client,
  accounts,
  transactions,
}: {
  client: FinanceApi;
  accounts: Account[];
  transactions: Transaction[];
}) {
  return (
    <>
      <AccountBalances client={client} accounts={accounts} />
      <Section title="Gastos por categoria" icon={PiggyBank}>
        <CategorySpendBreakdown transactions={transactions} />
      </Section>
    </>
  );
}

function AccountBalances({ client, accounts }: { client: FinanceApi; accounts: Account[] }) {
  const netWorth = useAsync(() => client.netWorth(), [client]);
  const balanceByAccount = useMemo(() => {
    const map = new Map<string, Balance>();
    for (const balance of netWorth.data?.accounts ?? []) {
      map.set(balance.account_id, balance);
    }
    return map;
  }, [netWorth.data]);

  return (
    <Section
      title="Saldo das contas"
      icon={Wallet}
      actions={<Button onClick={() => netWorth.run()}>Atualizar</Button>}
    >
      {netWorth.status === "error" && (
        <ErrorText>Não foi possível carregar os saldos.</ErrorText>
      )}
      {accounts.length === 0 ? (
        <p className="text-sm text-gray-500">Nenhuma conta cadastrada ainda.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {accounts.map((account) => {
            const balance = balanceByAccount.get(account.account_id);
            return (
              <li
                key={account.account_id}
                className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
              >
                <span className="font-medium">{account.name}</span>
                <span className="font-medium tabular-nums text-gray-900">
                  {moneySuffixed(balance?.balance_minor ?? 0, account.currency)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

// --- Configurações ---------------------------------------------------------

function SettingsTab({
  client,
  accounts,
}: {
  client: FinanceApi;
  accounts: AsyncResult<Account[]>;
}) {
  return (
    <>
      <UserProfile client={client} />
      <Accounts client={client} accounts={accounts} />
      <AlertPreferences client={client} />
      <BankImport client={client} />
    </>
  );
}

function UserProfile({ client }: { client: FinanceApi }) {
  const user = useAsync(() => client.me(), [client]);
  const [displayName, setDisplayName] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  useEffect(() => {
    if (user.data) setDisplayName(user.data.display_name);
  }, [user.data]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.updateCurrentUser({ display_name: displayName.trim() });
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  return (
    <Section title="Dados do usuário" icon={UserIcon}>
      {user.status === "error" && (
        <ErrorText>Não foi possível carregar os dados do usuário.</ErrorText>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="E-mail">
          <TextInput value={user.data?.email ?? ""} disabled readOnly />
        </Field>
        <Field label="Nome">
          <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
        </Field>
        <Button type="submit">Salvar</Button>
      </form>
      {status === "ok" && <p className="mt-3 text-sm text-green-700">Dados salvos.</p>}
      {status === "error" && <ErrorText>Não foi possível salvar os dados.</ErrorText>}
    </Section>
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
      setError("Não foi possível criar a conta.");
    }
  }

  return (
    <Section title="Contas" icon={Wallet}>
      <form onSubmit={create} className="mb-4 flex items-end gap-2">
        <Field label="Nome">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Moeda">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Button type="submit">Abrir conta</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {accounts.status === "error" && <ErrorText>Não foi possível carregar as contas.</ErrorText>}
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
      setResult(
        `${outcome.events_created} transação(ões) importada(s) (${outcome.skipped_duplicates} duplicada(s) ignorada(s)).`,
      );
    } catch (caught) {
      const status = (caught as { status?: number }).status;
      setError(
        status === 403
          ? "Conceda o consentimento 'bank' primeiro (página Consentimentos)."
          : "Não foi possível importar o CSV.",
      );
    }
  }

  return (
    <Section title="Importar extrato bancário (CSV)" icon={Receipt}>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <Field label="ID da conta">
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
          <Button type="submit">Importar</Button>
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
  const categories = useAsync(() => client.listCategories(), [client]);
  const [accountFilter, setAccountFilter] = useState("");
  const [kindFilter, setKindFilter] = useState<TxKindFilter>("all");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingTransactionId, setEditingTransactionId] = useState<string | null>(null);

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
        <StatCard
          label="Total de transações"
          value={String(totals.count)}
          icon={Calculator}
        />
        <StatCard label="Despesas" value={totals.expenses} tone="critical" icon={TrendingDown} />
        <StatCard label="Receitas" value={totals.income} tone="good" icon={TrendingUp} />
        <StatCard label="Saldo" value={totals.balance} icon={Scale} />
      </div>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <input
          type="search"
          aria-label="Buscar transações"
          placeholder="Buscar transações..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm sm:min-w-[220px] sm:flex-1"
        />
        <Select
          aria-label="Filtrar por conta"
          value={accountFilter}
          onChange={(e) => setAccountFilter(e.target.value)}
          className="w-full sm:w-auto"
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
          className="w-full sm:w-auto"
        >
          <option value="all">Todos os tipos</option>
          <option value="expense">Despesas manuais</option>
          <option value="import">Importadas</option>
        </Select>
        <Button onClick={() => setShowForm((v) => !v)} className="w-full sm:w-auto">
          {showForm ? "Cancelar" : "+ Nova Transação"}
        </Button>
      </div>

      {showForm && (
        <NewTransactionForm
          client={client}
          accounts={accounts}
          categories={categories.data ?? []}
          onCreated={() => {
            setShowForm(false);
            void transactions.run();
          }}
        />
      )}

      {editingTransactionId &&
        (() => {
          const editing = (transactions.data ?? []).find(
            (t) => t.event_id === editingTransactionId,
          );
          return editing ? (
            <EditTransactionForm
              client={client}
              transaction={editing}
              categories={categories.data ?? []}
              onSaved={() => {
                setEditingTransactionId(null);
                void transactions.run();
              }}
              onCancel={() => setEditingTransactionId(null)}
            />
          ) : null;
        })()}

      {transactions.status === "error" && (
        <ErrorText>Não foi possível carregar as transações.</ErrorText>
      )}
      <TransactionsTable
        transactions={filtered}
        accountName={accountName}
        loading={transactions.status === "loading"}
        onEdit={(t) => setEditingTransactionId(t.event_id)}
        onDelete={async (eventId) => {
          await client.deleteTransaction(eventId);
          void transactions.run();
        }}
      />
    </div>
  );
}

function NewTransactionForm({
  client,
  accounts,
  categories,
  onCreated,
}: {
  client: FinanceApi;
  accounts: Account[];
  categories: Category[];
  onCreated: () => void;
}) {
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [expenseType, setExpenseType] = useState<ExpenseType>("variable");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId && accounts.length > 0) setAccountId(accounts[0].account_id);
  }, [accounts, accountId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const parsedAmount = parseMoneyInput(amount);
    try {
      const input = {
        account_id: accountId,
        amount_minor: Math.abs(parsedAmount),
        currency: currency.trim().toUpperCase(),
        description: description.trim(),
        category: category.trim() || null,
      };
      if (parsedAmount < 0) {
        await client.recordExpense({ ...input, expense_type: expenseType });
      } else {
        await client.recordTransaction({ ...input, amount_minor: parsedAmount });
      }
      onCreated();
    } catch {
      setError("Não foi possível registrar a transação.");
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-4">
        <Field label="Conta">
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
            <option value="" disabled>
              Selecione uma conta
            </option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Valor">
          <TextInput
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full text-right tabular-nums"
            required
          />
        </Field>
        <Field label="Moeda">
          <TextInput
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full"
            required
          />
        </Field>
        <Field label="Descrição">
          <TextInput
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full"
            required
          />
        </Field>
        <Field label="Categoria">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.category_id} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Classificação">
          <Select
            value={expenseType}
            onChange={(e) => setExpenseType(e.target.value as ExpenseType)}
          >
            <option value="variable">Variável</option>
            <option value="fixed">Fixa</option>
          </Select>
        </Field>
        <Button type="submit" className="w-full sm:w-auto">
          Salvar
        </Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

function EditTransactionForm({
  client,
  transaction,
  categories,
  onSaved,
  onCancel,
}: {
  client: FinanceApi;
  transaction: Transaction;
  categories: Category[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [amount, setAmount] = useState((transaction.amount_minor / 100).toFixed(2));
  const [currency, setCurrency] = useState(transaction.currency);
  const [description, setDescription] = useState(transaction.description);
  const [category, setCategory] = useState(transaction.category ?? "");
  const [expenseType, setExpenseType] = useState<ExpenseType>(transaction.expense_type ?? "variable");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.updateTransaction(transaction.event_id, {
        amount_minor: parseMoneyInput(amount),
        currency: currency.trim().toUpperCase(),
        description: description.trim(),
        category: category.trim() || null,
        expense_type: expenseType,
      });
      onSaved();
    } catch {
      setError("Não foi possível salvar as alterações.");
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-900">Editar transação</h3>
      <form
        onSubmit={submit}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-4"
      >
        <Field label="Valor">
          <TextInput
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full text-right tabular-nums"
            required
          />
        </Field>
        <Field label="Moeda">
          <TextInput
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full"
            required
          />
        </Field>
        <Field label="Descrição">
          <TextInput
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full"
            required
          />
        </Field>
        <Field label="Categoria">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.category_id} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Classificação">
          <Select
            value={expenseType}
            onChange={(e) => setExpenseType(e.target.value as ExpenseType)}
          >
            <option value="variable">Variável</option>
            <option value="fixed">Fixa</option>
          </Select>
        </Field>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button type="submit" className="w-full sm:w-auto">
            Salvar
          </Button>
          <button
            type="button"
            onClick={onCancel}
            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:w-auto"
          >
            Cancelar edição
          </button>
        </div>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

function TransactionsTable({
  transactions,
  accountName,
  loading,
  onEdit,
  onDelete,
}: {
  transactions: Transaction[];
  accountName: (id: string) => string;
  loading: boolean;
  onEdit: (transaction: Transaction) => void;
  onDelete: (eventId: string) => void;
}) {
  if (loading && transactions.length === 0) {
    return <p className="text-sm text-gray-500">Carregando…</p>;
  }
  if (transactions.length === 0) {
    return <p className="text-sm text-gray-500">Nenhuma transação encontrada.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-4 py-2 font-medium">Descrição</th>
            <th className="px-4 py-2 font-medium">Categoria</th>
            <th className="px-4 py-2 font-medium">Classificação</th>
            <th className="px-4 py-2 font-medium">Conta</th>
            <th className="px-4 py-2 font-medium">Data</th>
            <th className="px-4 py-2 text-right font-medium">Valor</th>
            <th className="px-4 py-2 text-right font-medium">Ações</th>
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
              <td className="px-4 py-2.5 text-gray-500">
                {t.expense_type === "fixed"
                  ? "Fixa"
                  : t.expense_type === "variable"
                    ? "Variável"
                    : "—"}
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
              <td className="px-4 py-2.5">
                <span className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => onEdit(t)}
                    className="shrink-0 rounded-lg border border-blue-200 px-3 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50"
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(t.event_id)}
                    className="shrink-0 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50"
                  >
                    Excluir
                  </button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Categorias --------------------------------------------------------
//
// Cadastro de categorias — um pequeno registro reutilizável, como o de
// contas. O resumo de gastos por categoria vive na aba Visão geral.

const CATEGORIES_SCREENS: SubTabItem[] = [
  { id: "register", label: "Cadastrar categoria", icon: PlusCircle },
  { id: "list", label: "Categorias cadastradas", icon: ListChecks },
];

function CategoriesTab({ client }: { client: FinanceApi }) {
  const categories = useAsync(() => client.listCategories(), [client]);
  const [screen, setScreen] = useState(CATEGORIES_SCREENS[0].id);

  return (
    <>
      <SubTabs items={CATEGORIES_SCREENS} active={screen} onChange={setScreen} />
      {screen === "register" && (
        <RegisterCategory client={client} onRegistered={() => void categories.run()} />
      )}
      {screen === "list" && (
        <RegisteredCategoriesList
          client={client}
          categories={categories}
          onDeleted={() => void categories.run()}
        />
      )}
    </>
  );
}

function RegisterCategory({
  client,
  onRegistered,
}: {
  client: FinanceApi;
  onRegistered: () => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.createCategory(name.trim());
      setName("");
      onRegistered();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Você já tem uma categoria com esse nome."
          : "Não foi possível cadastrar a categoria.",
      );
    }
  }

  return (
    <Section title="Cadastrar categoria" icon={PlusCircle}>
      <form onSubmit={submit} className="flex items-end gap-2">
        <Field label="Nome">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Button type="submit">Cadastrar</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

function RegisteredCategoriesList({
  client,
  categories,
  onDeleted,
}: {
  client: FinanceApi;
  categories: AsyncResult<Category[]>;
  onDeleted: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  async function remove(categoryId: string) {
    setError(null);
    try {
      await client.deleteCategory(categoryId);
      onDeleted();
    } catch {
      setError("Não foi possível excluir a categoria.");
    }
  }

  return (
    <Section title="Categorias cadastradas" icon={ListChecks}>
      {categories.status === "error" && (
        <ErrorText>Não foi possível carregar as categorias.</ErrorText>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {categories.status === "ready" && categories.data?.length === 0 && (
        <p className="text-sm text-gray-500">Nenhuma categoria cadastrada ainda.</p>
      )}
      <ul className="flex flex-col gap-1 text-sm">
        {(categories.data ?? []).map((category) => (
          <li
            key={category.category_id}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
          >
            <CategoryBadge category={category.name} />
            <button
              type="button"
              onClick={() => void remove(category.category_id)}
              className="text-sm text-red-600 hover:underline"
            >
              Excluir
            </button>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function CategorySpendBreakdown({ transactions }: { transactions: Transaction[] }) {
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
        Nenhuma transação ainda — as categorias aparecerão aqui assim que você registrar alguma.
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
//
// Três telas dedicadas, cada uma com sua própria aba: (1) cadastro de uma
// nova conta, (2) a lista de contas cadastradas (definições) e (3) faturas e
// pagamento (ocorrências, com ação de pagar em um clique) — em vez de tudo
// empilhado numa única tela. Um resumo com KPIs fica sempre visível no
// topo, qualquer que seja a tela ativa. As preferências de alerta de
// vencimento vivem na aba Configurações.

const BILLS_SCREENS: SubTabItem[] = [
  { id: "register", label: "Cadastrar", icon: PlusCircle },
  { id: "list", label: "Contas cadastradas", icon: ListChecks },
  { id: "upcoming", label: "Faturas e pagamento", icon: Receipt },
];

function BillsTab({ client, accounts }: { client: FinanceApi; accounts: Account[] }) {
  const bills = useAsync(() => client.listBills(), [client]);
  const categories = useAsync(() => client.listCategories(), [client]);
  const [screen, setScreen] = useState(BILLS_SCREENS[0].id);

  return (
    <>
      <BillsSummary client={client} />
      <SubTabs items={BILLS_SCREENS} active={screen} onChange={setScreen} />
      {screen === "register" && (
        <RegisterBill
          client={client}
          accounts={accounts}
          categories={categories.data ?? []}
          onRegistered={() => void bills.run()}
        />
      )}
      {screen === "list" && (
        <RegisteredBillsList
          client={client}
          bills={bills}
          categories={categories.data ?? []}
          onCancelled={() => void bills.run()}
        />
      )}
      {screen === "upcoming" && <UpcomingBills client={client} />}
    </>
  );
}

function BillsSummary({ client }: { client: FinanceApi }) {
  const defaults = useMemo(defaultBillsWindow, []);
  const report = useAsync(
    () =>
      client.billsReport(
        new Date(defaults.from).toISOString(),
        new Date(defaults.to).toISOString(),
      ),
    [client, defaults.from, defaults.to],
  );

  const summary = useMemo(() => {
    const occurrences = report.data ?? [];
    const dueSoon = occurrences.filter((o) => !o.paid && !o.overdue);
    const overdue = occurrences.filter((o) => !o.paid && o.overdue);
    const paid = occurrences.filter((o) => o.paid);
    return {
      dueSoonCount: dueSoon.length,
      dueSoonTotal: moneyByCurrency(dueSoon),
      overdueCount: overdue.length,
      overdueTotal: moneyByCurrency(overdue),
      paidCount: paid.length,
      paidTotal: moneyByCurrency(paid),
    };
  }, [report.data]);

  return (
    <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <StatCard
        label="A vencer em breve"
        value={String(summary.dueSoonCount)}
        hint={summary.dueSoonTotal}
        tone="warning"
        icon={Clock}
      />
      <StatCard
        label="Vencidas"
        value={String(summary.overdueCount)}
        hint={summary.overdueTotal}
        tone="critical"
        icon={AlertTriangle}
      />
      <StatCard
        label="Pagas neste período"
        value={String(summary.paidCount)}
        hint={summary.paidTotal}
        tone="good"
        icon={CheckCircle2}
      />
    </div>
  );
}

function RegisterBill({
  client,
  accounts,
  categories,
  onRegistered,
}: {
  client: FinanceApi;
  accounts: Account[];
  categories: Category[];
  onRegistered: () => void;
}) {
  const [accountId, setAccountId] = useState("");
  const [payee, setPayee] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [category, setCategory] = useState("");
  const [recurrence, setRecurrence] = useState<BillRecurrence>("monthly");
  const [dueDay, setDueDay] = useState("5");
  const [dueAt, setDueAt] = useState("");
  const [maxOccurrences, setMaxOccurrences] = useState("0");
  const [occurrenceAnchor, setOccurrenceAnchor] = useState(currentYearMonth);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId && accounts.length > 0) setAccountId(accounts[0].account_id);
  }, [accounts, accountId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const anchor = parseYearMonth(occurrenceAnchor);
    try {
      await client.registerBill({
        account_id: accountId,
        payee: payee.trim(),
        amount_minor: parseMoneyInput(amount),
        currency: currency.trim().toUpperCase(),
        category: category.trim() || null,
        recurrence,
        due_day: recurrence === "monthly" ? Number(dueDay) : null,
        due_at: recurrence === "once" && dueAt ? new Date(dueAt).toISOString() : null,
        max_occurrences: Number(maxOccurrences) || 0,
        occurrence_anchor_year: anchor?.year ?? null,
        occurrence_anchor_month: anchor?.month ?? null,
      });
      setPayee("");
      setAmount("");
      setCategory("");
      setMaxOccurrences("0");
      setOccurrenceAnchor(currentYearMonth());
      onRegistered();
    } catch {
      setError("Não foi possível cadastrar a conta.");
    }
  }

  return (
    <Section title="Cadastrar conta a pagar" icon={PlusCircle}>
      <form
        onSubmit={submit}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-4"
      >
        <Field label="Conta">
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
            <option value="" disabled>
              Selecione uma conta
            </option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Beneficiário">
          <TextInput value={payee} onChange={(e) => setPayee(e.target.value)} required />
        </Field>
        <Field label="Valor">
          <TextInput
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="text-right tabular-nums"
            required
          />
        </Field>
        <Field label="Moeda">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Field label="Categoria">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.category_id} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Recorrência">
          <Select
            value={recurrence}
            onChange={(e) => setRecurrence(e.target.value as BillRecurrence)}
          >
            <option value="monthly">Mensal</option>
            <option value="once">Única</option>
          </Select>
        </Field>
        {recurrence === "monthly" ? (
          <Field label="Dia do vencimento">
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
          <Field label="Data de vencimento">
            <TextInput
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              required
            />
          </Field>
        )}
        <Field label="Ocorrências (0 = infinita)">
          <TextInput
            type="number"
            min={0}
            value={maxOccurrences}
            onChange={(e) => setMaxOccurrences(e.target.value)}
          />
        </Field>
        {recurrence === "monthly" && (
          <Field label="Mês/ano base das ocorrências">
            <TextInput
              type="month"
              value={occurrenceAnchor}
              onChange={(e) => setOccurrenceAnchor(e.target.value)}
            />
          </Field>
        )}
        <Button type="submit" className="w-full sm:w-auto">
          Cadastrar
        </Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

function RegisteredBillsList({
  client,
  bills,
  categories,
  onCancelled,
}: {
  client: FinanceApi;
  bills: AsyncResult<Bill[]>;
  categories: Category[];
  onCancelled: () => void;
}) {
  const [editingBillId, setEditingBillId] = useState<string | null>(null);

  async function cancel(billId: string) {
    await client.cancelBill(billId);
    onCancelled();
  }

  const editingBill = (bills.data ?? []).find((b) => b.bill_id === editingBillId) ?? null;

  return (
    <Section title="Contas cadastradas" icon={ListChecks}>
      {editingBill && (
        <EditBillForm
          client={client}
          bill={editingBill}
          categories={categories}
          onSaved={() => {
            setEditingBillId(null);
            onCancelled();
          }}
          onCancel={() => setEditingBillId(null)}
        />
      )}
      {bills.status === "error" && <ErrorText>Não foi possível carregar as contas.</ErrorText>}
      {bills.status === "ready" && (bills.data ?? []).length === 0 ? (
        <p className="text-sm text-gray-500">Nenhuma conta cadastrada ainda.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500">
                <th className="py-2 pr-3 font-medium">Beneficiário</th>
                <th className="py-2 pr-3 text-right font-medium">Valor</th>
                <th className="py-2 pr-3 font-medium">Vencimento</th>
                <th className="py-2 pr-3 font-medium">Categoria</th>
                <th className="py-2 pr-3 font-medium">Ocorrências</th>
                <th className="py-2 pl-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(bills.data ?? []).map((bill) => (
                <tr
                  key={bill.bill_id}
                  className={
                    "transition-colors hover:bg-gray-50" + (bill.active ? "" : " opacity-60")
                  }
                >
                  <td className="py-3 pr-3">
                    <span className="flex items-center gap-2">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                        <Wallet className="h-3.5 w-3.5" />
                      </span>
                      <span className="font-medium text-gray-900">{bill.payee}</span>
                      {!bill.active && (
                        <span className="text-xs text-gray-400">(cancelada)</span>
                      )}
                    </span>
                  </td>
                  <td className="py-3 pr-3 text-right tabular-nums text-gray-700">
                    {moneySuffixed(bill.amount_minor, bill.currency)}
                  </td>
                  <td className="py-3 pr-3 text-gray-700">
                    {bill.recurrence === "monthly"
                      ? `todo dia ${bill.due_day}`
                      : bill.due_at && shortDate(bill.due_at)}
                  </td>
                  <td className="py-3 pr-3">
                    {bill.category ? <CategoryBadge category={bill.category} /> : "—"}
                  </td>
                  <td className="py-3 pr-3 text-gray-700">
                    {bill.max_occurrences > 0 ? bill.max_occurrences : "Ilimitada"}
                  </td>
                  <td className="py-3 pl-3">
                    <span className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setEditingBillId(bill.bill_id)}
                        className="shrink-0 rounded-lg border border-blue-200 px-3 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50"
                      >
                        Editar
                      </button>
                      {bill.active && (
                        <button
                          type="button"
                          onClick={() => void cancel(bill.bill_id)}
                          className="shrink-0 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50"
                        >
                          Cancelar
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function EditBillForm({
  client,
  bill,
  categories,
  onSaved,
  onCancel,
}: {
  client: FinanceApi;
  bill: Bill;
  categories: Category[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [payee, setPayee] = useState(bill.payee);
  const [amount, setAmount] = useState((bill.amount_minor / 100).toFixed(2));
  const [currency, setCurrency] = useState(bill.currency);
  const [category, setCategory] = useState(bill.category ?? "");
  const [recurrence, setRecurrence] = useState<BillRecurrence>(bill.recurrence);
  const [dueDay, setDueDay] = useState(String(bill.due_day ?? 5));
  const [dueAt, setDueAt] = useState(bill.due_at ? toDatetimeLocal(new Date(bill.due_at)) : "");
  const [maxOccurrences, setMaxOccurrences] = useState(String(bill.max_occurrences));
  const [occurrenceAnchor, setOccurrenceAnchor] = useState(
    `${bill.occurrence_anchor_year}-${String(bill.occurrence_anchor_month).padStart(2, "0")}`,
  );
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const anchor = parseYearMonth(occurrenceAnchor);
    try {
      await client.updateBill(bill.bill_id, {
        payee: payee.trim(),
        amount_minor: parseMoneyInput(amount),
        currency: currency.trim().toUpperCase(),
        category: category.trim() || null,
        recurrence,
        due_day: recurrence === "monthly" ? Number(dueDay) : null,
        due_at: recurrence === "once" && dueAt ? new Date(dueAt).toISOString() : null,
        max_occurrences: Number(maxOccurrences) || 0,
        occurrence_anchor_year: anchor?.year ?? null,
        occurrence_anchor_month: anchor?.month ?? null,
      });
      onSaved();
    } catch {
      setError("Não foi possível salvar as alterações.");
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-900">Editar conta a pagar</h3>
      <form
        onSubmit={submit}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-4"
      >
        <Field label="Beneficiário">
          <TextInput value={payee} onChange={(e) => setPayee(e.target.value)} required />
        </Field>
        <Field label="Valor">
          <TextInput
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="text-right tabular-nums"
            required
          />
        </Field>
        <Field label="Moeda">
          <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} required />
        </Field>
        <Field label="Categoria">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Sem categoria</option>
            {categories.map((c) => (
              <option key={c.category_id} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Recorrência">
          <Select
            value={recurrence}
            onChange={(e) => setRecurrence(e.target.value as BillRecurrence)}
          >
            <option value="monthly">Mensal</option>
            <option value="once">Única</option>
          </Select>
        </Field>
        {recurrence === "monthly" ? (
          <Field label="Dia do vencimento">
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
          <Field label="Data de vencimento">
            <TextInput
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              required
            />
          </Field>
        )}
        <Field label="Ocorrências (0 = infinita)">
          <TextInput
            type="number"
            min={0}
            value={maxOccurrences}
            onChange={(e) => setMaxOccurrences(e.target.value)}
          />
        </Field>
        {recurrence === "monthly" && (
          <Field label="Mês/ano base das ocorrências">
            <TextInput
              type="month"
              value={occurrenceAnchor}
              onChange={(e) => setOccurrenceAnchor(e.target.value)}
            />
          </Field>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button type="submit" className="w-full sm:w-auto">
            Salvar
          </Button>
          <button
            type="button"
            onClick={onCancel}
            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:w-auto"
          >
            Cancelar edição
          </button>
        </div>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

function toDatetimeLocal(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

/** "YYYY-MM" for the current month — the default `type="month"` field value. */
function currentYearMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Parses a `type="month"` value ("YYYY-MM") into { year, month }. */
function parseYearMonth(value: string): { year: number; month: number } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) };
}

/** Do início do mês atual até o fim do próximo — uma janela útil por padrão. */
function defaultBillsWindow(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  const to = new Date(now.getFullYear(), now.getMonth() + 2, 0, 23, 59);
  return { from: toDatetimeLocal(from), to: toDatetimeLocal(to) };
}

function UpcomingBills({ client }: { client: FinanceApi }) {
  const defaults = useMemo(defaultBillsWindow, []);
  const [from, setFrom] = useState(defaults.from);
  const [to, setTo] = useState(defaults.to);
  const [paid, setPaid] = useState<"" | "true" | "false">("");
  const [overdue, setOverdue] = useState<"" | "true" | "false">("");
  const report = useAsync(
    () =>
      client.billsReport(new Date(from).toISOString(), new Date(to).toISOString(), {
        paid: paid === "" ? undefined : paid === "true",
        overdue: overdue === "" ? undefined : overdue === "true",
      }),
    [client, from, to, paid, overdue],
  );
  const [alertStatus, setAlertStatus] = useState<string | null>(null);
  const [payingKey, setPayingKey] = useState<string | null>(null);

  async function runAlerts() {
    setAlertStatus(null);
    try {
      const outcomes = await client.runBillAlerts();
      const sent = outcomes.filter((outcome) => outcome.delivered).length;
      setAlertStatus(`${sent} de ${outcomes.length} lembrete(s) enviado(s).`);
    } catch {
      setAlertStatus("Não foi possível executar os alertas.");
    }
  }

  async function markPaid(billId: string, dueAt: string, key: string) {
    setPayingKey(key);
    try {
      await client.payBill(billId, dueAt);
      await report.run();
    } finally {
      setPayingKey(null);
    }
  }

  return (
    <Section
      title="Faturas e pagamento"
      icon={CalendarClock}
      actions={
        <Button onClick={() => void runAlerts()} className="flex items-center gap-1.5">
          <Bell className="h-4 w-4" />
          Enviar alertas agora
        </Button>
      }
    >
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="De">
          <TextInput
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </Field>
        <Field label="Até">
          <TextInput type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
        <Field label="Status">
          <Select value={paid} onChange={(e) => setPaid(e.target.value as typeof paid)}>
            <option value="">Todas</option>
            <option value="true">Pagas</option>
            <option value="false">Não pagas</option>
          </Select>
        </Field>
        <Field label="Vencimento">
          <Select value={overdue} onChange={(e) => setOverdue(e.target.value as typeof overdue)}>
            <option value="">Todas</option>
            <option value="true">Vencidas</option>
            <option value="false">Não vencidas</option>
          </Select>
        </Field>
      </div>
      {alertStatus && <p className="mb-2 text-sm text-gray-700">{alertStatus}</p>}
      {report.status === "error" && <ErrorText>Não foi possível carregar as faturas.</ErrorText>}
      <ul className="flex flex-col gap-2 text-sm">
        {(report.data ?? []).map((occurrence) => {
          const key = `${occurrence.bill_id}-${occurrence.period}`;
          const StatusIcon = occurrence.paid ? CheckCircle2 : occurrence.overdue ? AlertTriangle : Clock;
          const accent = occurrence.paid
            ? "border-l-green-500 bg-green-50/40"
            : occurrence.overdue
              ? "border-l-red-500 bg-red-50/40"
              : "border-l-amber-400 bg-amber-50/30";
          const statusTextClass = occurrence.paid
            ? "text-green-700"
            : occurrence.overdue
              ? "text-red-600"
              : "text-amber-600";
          return (
            <li
              key={key}
              className={
                "flex items-center justify-between gap-2 rounded-lg border border-gray-200 border-l-4 px-4 py-3 transition-colors hover:bg-gray-50 " +
                accent
              }
            >
              <span className="flex flex-wrap items-center gap-2">
                <StatusIcon className={"h-4 w-4 shrink-0 " + statusTextClass} />
                <span className="font-medium text-gray-900">{occurrence.payee}</span>
                <span className="text-gray-500">
                  · {money(occurrence.amount_minor, occurrence.currency)} · vence em{" "}
                  {shortDate(occurrence.due_at)}
                </span>
                {occurrence.category && <CategoryBadge category={occurrence.category} />}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <span className={"text-xs font-medium " + statusTextClass}>
                  {occurrence.paid ? "Paga" : occurrence.overdue ? "Vencida" : "A vencer"}
                </span>
                {!occurrence.paid && (
                  <button
                    type="button"
                    onClick={() => void markPaid(occurrence.bill_id, occurrence.due_at, key)}
                    disabled={payingKey === key}
                    className="rounded-lg border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 transition-colors hover:bg-green-50 disabled:opacity-50"
                  >
                    {payingKey === key ? "Marcando…" : "Marcar como paga"}
                  </button>
                )}
              </span>
            </li>
          );
        })}
        {report.status === "ready" && (report.data ?? []).length === 0 && (
          <li className="text-gray-500">Nenhuma fatura no período selecionado.</li>
        )}
      </ul>
    </Section>
  );
}

function AlertPreferences({ client }: { client: FinanceApi }) {
  const preference = useAsync(() => client.getNotificationPreferences(), [client]);
  const alertEmails = useAsync(() => client.listAlertEmails(), [client]);
  const alertPhones = useAsync(() => client.listAlertPhones(), [client]);
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [contactError, setContactError] = useState<string | null>(null);

  useEffect(() => {
    if (preference.data) {
      setEmailEnabled(preference.data.email_enabled);
      setWhatsappEnabled(preference.data.whatsapp_enabled);
    }
  }, [preference.data]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.setNotificationPreferences({
        email_enabled: emailEnabled,
        whatsapp_enabled: whatsappEnabled,
      });
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  async function addEmail(event: FormEvent) {
    event.preventDefault();
    setContactError(null);
    try {
      await client.addAlertEmail(newEmail.trim());
      setNewEmail("");
      await alertEmails.run();
    } catch (err) {
      setContactError(
        err instanceof ApiError && err.status === 409
          ? "Esse e-mail já está cadastrado."
          : "Não foi possível cadastrar o e-mail.",
      );
    }
  }

  async function removeEmail(alertEmailId: string) {
    await client.deleteAlertEmail(alertEmailId);
    await alertEmails.run();
  }

  async function addPhone(event: FormEvent) {
    event.preventDefault();
    setContactError(null);
    try {
      await client.addAlertPhone(newPhone.trim());
      setNewPhone("");
      await alertPhones.run();
    } catch (err) {
      setContactError(
        err instanceof ApiError && err.status === 409
          ? "Esse telefone já está cadastrado."
          : "Não foi possível cadastrar o telefone.",
      );
    }
  }

  async function removePhone(alertPhoneId: string) {
    await client.deleteAlertPhone(alertPhoneId);
    await alertPhones.run();
  }

  return (
    <Section title="Preferências de alerta de vencimento" icon={Bell}>
      <p className="mb-4 text-sm text-gray-500">
        Escolha como você quer ser avisado quando uma conta estiver perto de vencer ou vencida.
      </p>
      <form onSubmit={submit} className="mb-6 flex flex-wrap items-end gap-3">
        <label
          className={
            "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors " +
            (emailEnabled
              ? "border-blue-200 bg-blue-50 text-blue-700"
              : "border-gray-200 text-gray-600 hover:bg-gray-50")
          }
        >
          <input
            type="checkbox"
            checked={emailEnabled}
            onChange={(e) => setEmailEnabled(e.target.checked)}
            className="sr-only"
          />
          <Bell className="h-4 w-4" />
          E-mail
        </label>
        <label
          className={
            "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors " +
            (whatsappEnabled
              ? "border-blue-200 bg-blue-50 text-blue-700"
              : "border-gray-200 text-gray-600 hover:bg-gray-50")
          }
        >
          <input
            type="checkbox"
            checked={whatsappEnabled}
            onChange={(e) => setWhatsappEnabled(e.target.checked)}
            className="sr-only"
          />
          <Bell className="h-4 w-4" />
          WhatsApp
        </label>
        <Button type="submit">Salvar</Button>
      </form>
      {status === "ok" && <p className="mb-4 text-sm text-green-700">Preferências salvas.</p>}
      {status === "error" && (
        <ErrorText>Não foi possível salvar as preferências.</ErrorText>
      )}

      {contactError && <ErrorText>{contactError}</ErrorText>}

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-900">E-mails de alerta</h3>
          <form onSubmit={addEmail} className="mb-2 flex items-end gap-2">
            <Field label="E-mail de alerta">
              <TextInput
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="alguem@exemplo.com"
                required
              />
            </Field>
            <Button type="submit">Adicionar</Button>
          </form>
          {alertEmails.status === "error" && (
            <ErrorText>Não foi possível carregar os e-mails.</ErrorText>
          )}
          {alertEmails.status === "ready" && (alertEmails.data ?? []).length === 0 && (
            <p className="text-sm text-gray-500">Nenhum e-mail cadastrado ainda.</p>
          )}
          <ul className="flex flex-col gap-1 text-sm">
            {(alertEmails.data ?? []).map((entry: AlertEmail) => (
              <li
                key={entry.alert_email_id}
                className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
              >
                <span>{entry.email}</span>
                <button
                  type="button"
                  onClick={() => void removeEmail(entry.alert_email_id)}
                  className="text-sm text-red-600 hover:underline"
                >
                  Excluir
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-900">Telefones (WhatsApp)</h3>
          <form onSubmit={addPhone} className="mb-2 flex items-end gap-2">
            <Field label="Número do WhatsApp">
              <TextInput
                value={newPhone}
                onChange={(e) => setNewPhone(e.target.value)}
                placeholder="+5511999999999"
                required
              />
            </Field>
            <Button type="submit">Adicionar</Button>
          </form>
          {alertPhones.status === "error" && (
            <ErrorText>Não foi possível carregar os telefones.</ErrorText>
          )}
          {alertPhones.status === "ready" && (alertPhones.data ?? []).length === 0 && (
            <p className="text-sm text-gray-500">Nenhum telefone cadastrado ainda.</p>
          )}
          <ul className="flex flex-col gap-1 text-sm">
            {(alertPhones.data ?? []).map((entry: AlertPhone) => (
              <li
                key={entry.alert_phone_id}
                className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
              >
                <span>{entry.phone}</span>
                <button
                  type="button"
                  onClick={() => void removePhone(entry.alert_phone_id)}
                  className="text-sm text-red-600 hover:underline"
                >
                  Excluir
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}
