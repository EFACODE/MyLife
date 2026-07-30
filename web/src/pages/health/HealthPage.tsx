import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

type HealthApi = Pick<
  ApiClient,
  "listSleep" | "recordSleep" | "listWorkouts" | "recordWorkout" | "importHealth"
>;

function nowLocal(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function HealthPage() {
  const client = useApiClient();
  return (
    <>
      <SleepSection client={client} />
      <WorkoutSection client={client} />
      <HealthImport client={client} />
    </>
  );
}

function SleepSection({ client }: { client: HealthApi }) {
  const sleep = useAsync(() => client.listSleep(), [client]);
  const [occurredAt, setOccurredAt] = useState(nowLocal);
  const [minutes, setMinutes] = useState("");
  const [quality, setQuality] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.recordSleep({
        occurred_at: new Date(occurredAt).toISOString(),
        duration_minutes: Number(minutes),
        quality: quality.trim() || null,
      });
      setMinutes("");
      setQuality("");
      await sleep.run();
    } catch {
      setError("Could not record sleep.");
    }
  }

  return (
    <Section title="Sleep">
      <form onSubmit={submit} className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Occurred at">
          <TextInput
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            required
          />
        </Field>
        <Field label="Duration (minutes)">
          <TextInput
            type="number"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            required
          />
        </Field>
        <Field label="Quality">
          <TextInput value={quality} onChange={(e) => setQuality(e.target.value)} />
        </Field>
        <Button type="submit">Record sleep</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(sleep.data ?? []).map((session) => (
          <li key={session.event_id} className="rounded border border-gray-200 px-3 py-2">
            {session.duration_minutes} min
            {session.quality && <span className="text-gray-500"> · {session.quality}</span>}
            <span className="text-gray-500">
              {" · "}
              {new Date(session.occurred_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function WorkoutSection({ client }: { client: HealthApi }) {
  const workouts = useAsync(() => client.listWorkouts(), [client]);
  const [occurredAt, setOccurredAt] = useState(nowLocal);
  const [activity, setActivity] = useState("");
  const [minutes, setMinutes] = useState("");
  const [distance, setDistance] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.recordWorkout({
        occurred_at: new Date(occurredAt).toISOString(),
        activity: activity.trim(),
        duration_minutes: Number(minutes),
        distance_meters: distance ? Number(distance) : null,
      });
      setActivity("");
      setMinutes("");
      setDistance("");
      await workouts.run();
    } catch {
      setError("Could not record the workout.");
    }
  }

  return (
    <Section title="Workouts">
      <form onSubmit={submit} className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Occurred at">
          <TextInput
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            required
          />
        </Field>
        <Field label="Activity">
          <TextInput value={activity} onChange={(e) => setActivity(e.target.value)} required />
        </Field>
        <Field label="Duration (minutes)">
          <TextInput
            type="number"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            required
          />
        </Field>
        <Field label="Distance (meters)">
          <TextInput
            type="number"
            value={distance}
            onChange={(e) => setDistance(e.target.value)}
          />
        </Field>
        <Button type="submit">Record workout</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      <ul className="flex flex-col gap-1 text-sm">
        {(workouts.data ?? []).map((workout) => (
          <li key={workout.event_id} className="rounded border border-gray-200 px-3 py-2">
            <span className="font-medium">{workout.activity}</span> · {workout.duration_minutes} min
            {workout.distance_meters !== null && (
              <span className="text-gray-500"> · {workout.distance_meters} m</span>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function HealthImport({ client }: { client: HealthApi }) {
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    try {
      const outcome = await client.importHealth(csv);
      setResult(`Imported ${outcome.events_created} (skipped ${outcome.skipped_duplicates}).`);
    } catch (caught) {
      const status = (caught as { status?: number }).status;
      setError(
        status === 403
          ? "Grant the 'health' consent first (Consent page)."
          : "Could not import the CSV.",
      );
    }
  }

  return (
    <Section title="Health CSV import">
      <form onSubmit={submit} className="flex flex-col gap-2">
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
