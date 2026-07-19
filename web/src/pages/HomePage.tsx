import { useEffect, useState } from "react";

import type { User } from "../api/types";
import { useApiClient } from "../api/useApiClient";
import { Briefing } from "../components/Briefing";
import { Header } from "../components/Header";
import { Timeline } from "../components/Timeline";

type Status = "loading" | "ready" | "error";

export function HomePage() {
  const client = useApiClient();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let active = true;
    client
      .me()
      .then((resolved) => {
        if (active) {
          setUser(resolved);
          setStatus("ready");
        }
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client]);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-2xl px-4 py-8">
        {status === "loading" && <p className="text-sm text-gray-500">Loading…</p>}
        {status === "error" && (
          <p role="alert" className="text-sm text-red-600">
            Could not load your account.
          </p>
        )}
        {status === "ready" && user && (
          <>
            <h1 className="mb-6 text-xl font-semibold">Welcome, {user.display_name}</h1>
            <Briefing client={client} userId={user.user_id} />
            <Timeline client={client} userId={user.user_id} />
          </>
        )}
      </main>
    </div>
  );
}
