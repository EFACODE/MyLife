import { useState, type FormEvent } from "react";

import { useApiClient } from "../../api/useApiClient";
import { useMe } from "../../auth/MeContext";
import { Timeline } from "../../components/Timeline";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";

function localNow(): string {
  // yyyy-MM-ddThh:mm for a datetime-local input, in local time.
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

export function CapturePage() {
  const client = useApiClient();
  const { user, status } = useMe();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [note, setNote] = useState("");
  const [occurredAt, setOccurredAt] = useState(localNow);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  if (status === "loading" || status === "idle")
    return <p className="text-sm text-gray-500">Carregando…</p>;
  if (status === "error" || !user) return <ErrorText>Não foi possível carregar sua conta.</ErrorText>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    setError(null);
    try {
      await client.captureEvent({
        user_id: user.user_id,
        occurred_at: new Date(occurredAt).toISOString(),
        title: title.trim(),
        category: category.trim(),
        note: note.trim() || null,
      });
      setTitle("");
      setCategory("");
      setNote("");
      setReloadKey((key) => key + 1);
    } catch {
      setError("Não foi possível registrar o evento.");
    }
  }

  return (
    <>
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
      <Timeline key={reloadKey} client={client} userId={user.user_id} />
    </>
  );
}
