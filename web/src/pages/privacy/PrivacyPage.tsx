import { useState } from "react";

import type { ExportBundle } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Section } from "../../components/ui/Section";

const EXPORT_COUNTS: (keyof ExportBundle)[] = [
  "consents",
  "audit",
  "events",
  "raw_records",
  "entities",
  "relationships",
  "accounts",
  "goals",
  "documents",
];

export function PrivacyPage() {
  const client = useApiClient();
  const { logout } = useAuth();
  const [bundle, setBundle] = useState<ExportBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function exportData() {
    setError(null);
    try {
      setBundle(await client.exportMe());
    } catch {
      setError("Could not export your data.");
    }
  }

  async function erase() {
    setError(null);
    try {
      await client.deleteMe();
      logout(); // token cleared → RequireAuth redirects to /login
    } catch {
      setError("Could not erase your account.");
    }
  }

  return (
    <>
      <Section title="Export my data" actions={<Button onClick={exportData}>Export</Button>}>
        {error && <ErrorText>{error}</ErrorText>}
        {bundle ? (
          <ul className="flex flex-col gap-1 text-sm">
            {EXPORT_COUNTS.map((key) => (
              <li key={key}>
                <span className="font-medium">{key}</span>:{" "}
                {(bundle[key] as unknown[]).length}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">
            Export a copy of everything the platform holds about you.
          </p>
        )}
      </Section>

      <Section title="Erase my account">
        <p className="mb-3 text-sm text-gray-600">
          This permanently deletes your account and all associated data.
        </p>
        {!confirming ? (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
          >
            Erase account
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-red-600">Are you sure? This cannot be undone.</span>
            <button
              type="button"
              onClick={erase}
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white"
            >
              Confirm erase
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-sm text-gray-600 hover:underline"
            >
              Cancel
            </button>
          </div>
        )}
      </Section>
    </>
  );
}
