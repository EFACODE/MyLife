import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../api/client";
import type { TimelineEvent } from "../api/types";

export type TimelineApi = Pick<ApiClient, "getTimeline">;

type Status = "loading" | "ready" | "error";

export function Timeline({ client, userId }: { client: TimelineApi; userId: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState<Status>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const page = await client.getTimeline(userId, filter ? { eventType: filter } : {});
      setEvents(page.items);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, [client, userId, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Timeline</h2>
        <input
          aria-label="Filter by event type"
          placeholder="event type…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>
      {status === "loading" && <p className="text-sm text-gray-500">Loading…</p>}
      {status === "error" && (
        <p role="alert" className="text-sm text-red-600">
          Could not load the timeline.
        </p>
      )}
      {status === "ready" && events.length === 0 && (
        <p className="text-sm text-gray-500">No events yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {events.map((event) => (
          <li key={event.event_id} className="rounded border border-gray-200 px-3 py-2 text-sm">
            <span className="font-medium">{event.event_type}</span>
            <span className="text-gray-500">
              {" · "}
              {new Date(event.occurred_at).toLocaleString()}
              {" · "}
              {event.source}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
