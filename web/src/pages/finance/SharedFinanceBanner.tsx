import { Users } from "lucide-react";

import { useApiClient } from "../../api/useApiClient";
import { useOptionalMe } from "../../auth/MeContext";
import { useAsync } from "../../lib/useAsync";

/**
 * Tells a user-group member whose Finance ledger they are looking at (T2.6):
 * every member of a group reads and writes the group owner's Finance data.
 * Renders nothing outside a group (or if the group can't be loaded).
 */
export function SharedFinanceBanner() {
  const client = useApiClient();
  const user = useOptionalMe()?.user ?? null;
  const group = useAsync(() => client.myGroup(), [client]);
  const data = group.data;
  if (group.status !== "ready" || !data) return null;

  const owner = data.members.find((m) => m.user_id === data.owner_user_id);
  const others = data.members.filter((m) => m.user_id !== user?.user_id);
  const isOwner = user?.user_id === data.owner_user_id;

  return (
    <div
      role="status"
      className="mb-4 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900"
    >
      <Users className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>
        <span className="font-medium">Finanças compartilhadas · {data.name}.</span>{" "}
        {isOwner
          ? `Seus dados de Finanças são compartilhados com ${others.map((m) => m.display_name).join(", ") || "o grupo"}.`
          : `Você está vendo e editando os dados de Finanças de ${owner?.display_name ?? "titular do grupo"}.`}
      </span>
    </div>
  );
}
