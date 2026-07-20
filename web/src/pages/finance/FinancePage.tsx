import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { money } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

type FinanceApi = Pick<
  ApiClient,
  "listAccounts" | "createAccount" | "recordExpense" | "netWorth" | "cashFlow" | "importBank"
>;

export function FinancePage() {
  const client = useApiClient();
  return (
    <>
      <Accounts client={client} />
      <RecordExpense client={client} />
      <NetWorthView client={client} />
      <CashFlowView client={client} />
      <BankImport client={client} />
    </>
  );
}

function Accounts({ client }: { client: FinanceApi }) {
  const accounts = useAsync(() => client.listAccounts(), [client]);
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

function RecordExpense({ client }: { client: FinanceApi }) {
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.recordExpense({
        account_id: accountId.trim(),
        amount_minor: Number(amount),
        currency: currency.trim().toUpperCase(),
        description: description.trim(),
        category: category.trim() || null,
      });
      setAmount("");
      setDescription("");
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  return (
    <Section title="Record expense">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Account id">
          <TextInput value={accountId} onChange={(e) => setAccountId(e.target.value)} required />
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
        <Button type="submit">Record</Button>
      </form>
      {status === "ok" && <p className="mt-2 text-sm text-green-700">Recorded.</p>}
      {status === "error" && <ErrorText>Could not record the expense.</ErrorText>}
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
