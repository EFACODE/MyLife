import { useState } from "react";

import type { ApiClient } from "../api/client";
import type { Briefing as BriefingModel } from "../api/types";

export type BriefingApi = Pick<ApiClient, "deliverBriefing">;

type Status = "idle" | "loading" | "error";

export function Briefing({ client, userId }: { client: BriefingApi; userId: string }) {
  const [briefing, setBriefing] = useState<BriefingModel | null>(null);
  const [status, setStatus] = useState<Status>("idle");

  async function deliver() {
    setStatus("loading");
    try {
      setBriefing(await client.deliverBriefing(userId));
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Resumo diário</h2>
        <button
          type="button"
          onClick={() => void deliver()}
          disabled={status === "loading"}
          className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {status === "loading" ? "Enviando…" : "Enviar resumo"}
        </button>
      </div>
      {status === "error" && (
        <p role="alert" className="text-sm text-red-600">
          Não foi possível enviar o resumo.
        </p>
      )}
      {briefing && (
        <div>
          <p className="text-sm text-gray-500">
            {briefing.event_count} eventos nas últimas {briefing.window_hours}h
          </p>
          {briefing.lines.length === 0 ? (
            <p className="mt-2 text-sm text-gray-500">Nada notável nesse período.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              {briefing.lines.map((line, index) => (
                <li
                  key={`${line.kind}-${index}`}
                  className="rounded border border-gray-200 px-3 py-2 text-sm"
                >
                  <span className="font-medium">{line.kind}</span>: {line.summary}
                  <span className="text-gray-500"> ({line.evidence.length} evidências)</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
