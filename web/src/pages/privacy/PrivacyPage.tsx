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
  "categories",
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
      setError("Não foi possível exportar seus dados.");
    }
  }

  async function erase() {
    setError(null);
    try {
      await client.deleteMe();
      logout(); // token cleared → RequireAuth redirects to /login
    } catch {
      setError("Não foi possível apagar sua conta.");
    }
  }

  return (
    <>
      <Section title="Exportar meus dados" actions={<Button onClick={exportData}>Exportar</Button>}>
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
            Exporte uma cópia de tudo o que a plataforma guarda sobre você.
          </p>
        )}
      </Section>

      <Section title="Apagar minha conta">
        <p className="mb-3 text-sm text-gray-600">
          Isso apaga permanentemente sua conta e todos os dados associados.
        </p>
        {!confirming ? (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
          >
            Apagar conta
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-red-600">Tem certeza? Isso não pode ser desfeito.</span>
            <button
              type="button"
              onClick={erase}
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white"
            >
              Confirmar exclusão
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-sm text-gray-600 hover:underline"
            >
              Cancelar
            </button>
          </div>
        )}
      </Section>
    </>
  );
}
