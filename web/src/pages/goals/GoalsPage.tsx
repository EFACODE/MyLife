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
      <Section title="Progress">
        {progress.status === "error" && <ErrorText>Could not load progress.</ErrorText>}
        {progress.status === "ready" && progress.data?.length === 0 && (
          <p className="text-sm text-gray-500">No goals yet.</p>
        )}
        <ul className="flex flex-col gap-2">
          {(progress.data ?? []).map((row) => (
            <li key={row.goal_id} className="rounded border border-gray-200 px-3 py-2 text-sm">
              <span className="font-medium">{titles.get(row.goal_id) ?? row.metric}</span> ·{" "}
              {row.current_value}/{row.target_value} {row.metric} (
              {Math.round(row.progress_ratio * 100)}%){row.achieved && " · ✅ achieved"}
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
      setError("Could not create the goal.");
    }
  }

  return (
    <Section title="Create goal">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Title">
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field label="Metric">
          <TextInput value={metric} onChange={(e) => setMetric(e.target.value)} required />
        </Field>
        <Field label="Target value">
          <TextInput
            type="number"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            required
          />
        </Field>
        <Field label="Unit">
          <TextInput value={unit} onChange={(e) => setUnit(e.target.value)} required />
        </Field>
        <Button type="submit">Create</Button>
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
      setError("Could not record the milestone.");
    }
  }

  return (
    <Section title="Record milestone">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Goal id">
          <TextInput value={goalId} onChange={(e) => setGoalId(e.target.value)} required />
        </Field>
        <Field label="Value">
          <TextInput
            type="number"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </Field>
        <Field label="Note">
          <TextInput value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Button type="submit">Record</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}
