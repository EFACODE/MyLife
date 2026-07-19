import { useApiClient } from "../../api/useApiClient";
import { ErrorText } from "../../components/ui/ErrorText";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

export function AuditPage() {
  const client = useApiClient();
  const audit = useAsync(() => client.getAudit(), [client]);

  return (
    <Section title="Audit log">
      {audit.status === "loading" && <p className="text-sm text-gray-500">Loading…</p>}
      {audit.status === "error" && <ErrorText>Could not load the audit log.</ErrorText>}
      {audit.status === "ready" && audit.data && audit.data.length === 0 && (
        <p className="text-sm text-gray-500">No audit entries yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {(audit.data ?? []).map((entry) => (
          <li key={entry.audit_id} className="rounded border border-gray-200 px-3 py-2 text-sm">
            <span className="font-medium">{entry.action}</span>
            {entry.resource && <span className="text-gray-500"> · {entry.resource}</span>}
            <span className="text-gray-500"> · {new Date(entry.occurred_at).toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
