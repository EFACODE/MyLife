import { createContext, useContext, type ReactNode } from "react";

import type { User } from "../api/types";
import { useApiClient } from "../api/useApiClient";
import { useAsync, type AsyncStatus } from "../lib/useAsync";

interface MeValue {
  user: User | null;
  status: AsyncStatus;
}

const MeContext = createContext<MeValue | null>(null);

/** Resolve the signed-in user once and share it with the app. */
export function MeProvider({ children }: { children: ReactNode }) {
  const client = useApiClient();
  const { data, status } = useAsync(() => client.me(), [client]);
  return <MeContext.Provider value={{ user: data, status }}>{children}</MeContext.Provider>;
}

export function useMe(): MeValue {
  const ctx = useContext(MeContext);
  if (!ctx) throw new Error("useMe must be used within a MeProvider");
  return ctx;
}
