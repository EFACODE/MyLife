import { useMemo, useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

type GoalsApi = Pick<
  ApiClient,
  "listGoals" | "createGoal" | "goalProgressAll" | "recordMilestone"
>;

export function GoalsPage() {
  const client = useApiClient();
  const goals = useAsync(() => client.listGoals(), [client]);
  const progress = useAsync(() => client.goalProgressAll(), [client]);
  const titles = useMemo(
    () => new Map((goals.data ?? []).map((goal) => [goal.goal_id, goal.title])),
    [goals.data],
  );

  async function reload() {
    await Promise.all([goals.run(), progress.run()]);
  }

  return (
    <>
      <CreateGoal client={client} onCreated={reload} />
      <Section title="Progresso">
        {progress.status === "error" && <ErrorText>Não foi possível carregar o progresso.</ErrorText>}
        {progress.status === "ready" && progress.data?.length === 0 && (
          <p className="text-sm text-gray-500">Nenhuma meta ainda.</p>
        )}
        <ul className="flex flex-col gap-2">
          {(progress.data ?? []).map((row) => (
            <li key={row.goal_id} className="rounded border border-gray-200 px-3 py-2 text-sm">
              <span className="font-medium">{titles.get(row.goal_id) ?? row.metric}</span> ·{" "}
              {row.current_value}/{row.target_value} {row.metric} (
              {Math.round(row.progress_ratio * 100)}%){row.achieved && " · ✅ atingida"}
            </li>
          ))}
        </ul>
      </Section>
      <RecordMilestone client={client} onRecorded={reload} />
    </>
  );
}

function CreateGoal({ client, onCreated }: { client: GoalsApi; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [metric, setMetric] = useState("");
  const [target, setTarget] = useState("");
  const [unit, setUnit] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.createGoal({
        title: title.trim(),
        metric: metric.trim(),
        target_value: Number(target),
        unit: unit.trim(),
      });
      setTitle("");
      setMetric("");
      setTarget("");
      setUnit("");
      onCreated();
    } catch {
      setError("Não foi possível criar a meta.");
    }
  }

  return (
    <Section title="Criar meta">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Título">
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field label="Métrica">
          <TextInput value={metric} onChange={(e) => setMetric(e.target.value)} required />
        </Field>
        <Field label="Valor alvo">
          <TextInput
            type="number"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            required
          />
        </Field>
        <Field label="Unidade">
          <TextInput value={unit} onChange={(e) => setUnit(e.target.value)} required />
        </Field>
        <Button type="submit">Criar</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

function RecordMilestone({ client, onRecorded }: { client: GoalsApi; onRecorded: () => void }) {
  const [goalId, setGoalId] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.recordMilestone(goalId.trim(), Number(value), note.trim() || null);
      setValue("");
      setNote("");
      onRecorded();
    } catch {
      setError("Não foi possível registrar o marco.");
    }
  }

  return (
    <Section title="Registrar marco">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Id da meta">
          <TextInput value={goalId} onChange={(e) => setGoalId(e.target.value)} required />
        </Field>
        <Field label="Valor">
          <TextInput
            type="number"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </Field>
        <Field label="Nota">
          <TextInput value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Button type="submit">Registrar</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}
