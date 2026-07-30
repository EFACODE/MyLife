import { useState, type FormEvent } from "react";

import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

export function ConsentPage() {
  const client = useApiClient();
  const consents = useAsync(() => client.listConsents(), [client]);
  const [scope, setScope] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function grant(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.grantConsent(scope.trim());
      setScope("");
      await consents.run();
    } catch {
      setError("Could not grant consent.");
    }
  }

  async function revoke(target: string) {
    setError(null);
    try {
      await client.revokeConsent(target);
      await consents.run();
    } catch {
      setError("Could not revoke consent.");
    }
  }

  return (
    <Section title="Consent">
      <form onSubmit={grant} className="mb-4 flex items-end gap-2">
        <Field label="Scope (e.g. bank, health)">
          <TextInput value={scope} onChange={(e) => setScope(e.target.value)} required />
        </Field>
        <Button type="submit">Grant</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {consents.status === "loading" && <p className="text-sm text-gray-500">Loading…</p>}
      {consents.status === "error" && <ErrorText>Could not load consents.</ErrorText>}
      {consents.status === "ready" && consents.data && consents.data.length === 0 && (
        <p className="text-sm text-gray-500">No consents granted yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {(consents.data ?? []).map((consent) => (
          <li
            key={consent.scope}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-sm"
          >
            <span>
              <span className="font-medium">{consent.scope}</span>
              <span className="text-gray-500"> · {consent.granted ? "granted" : "revoked"}</span>
            </span>
            {consent.granted && (
              <button
                type="button"
                onClick={() => revoke(consent.scope)}
                className="text-sm text-red-600 hover:underline"
              >
                Revoke
              </button>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}
