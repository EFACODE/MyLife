import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";

export type CaptureApi = Pick<ApiClient, "captureEvent">;

function localNow(): string {
  // yyyy-MM-ddThh:mm for a datetime-local input, in local time.
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

/** Manual Life Event capture (`POST /timeline/events`), shown on the Painel. */
export function CaptureEventForm({
  client,
  userId,
  onCaptured,
}: {
  client: CaptureApi;
  userId: string;
  onCaptured: () => void;
}) {
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [note, setNote] = useState("");
  const [occurredAt, setOccurredAt] = useState(localNow);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.captureEvent({
        user_id: userId,
        occurred_at: new Date(occurredAt).toISOString(),
        title: title.trim(),
        category: category.trim(),
        note: note.trim() || null,
      });
      setTitle("");
      setCategory("");
      setNote("");
      onCaptured();
    } catch {
      setError("Não foi possível registrar o evento.");
    }
  }

  return (
    <Section title="Registrar evento">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="Título">
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field label="Categoria">
          <TextInput value={category} onChange={(e) => setCategory(e.target.value)} required />
        </Field>
        <Field label="Nota (opcional)">
          <TextInput value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Field label="Ocorrido em">
          <TextInput
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            required
          />
        </Field>
        {error && <ErrorText>{error}</ErrorText>}
        <div>
          <Button type="submit">Registrar evento</Button>
        </div>
      </form>
    </Section>
  );
}
