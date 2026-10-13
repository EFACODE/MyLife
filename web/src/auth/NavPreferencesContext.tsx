import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { useApiClient } from "../api/useApiClient";
import type { NavPreference } from "../nav";

interface NavPreferencesValue {
  /** The saved preference; `null` only while loading (a failed load yields the default). */
  preference: NavPreference | null;
  /** Persist a new preference and apply it to the sidebar. */
  save: (preference: NavPreference) => Promise<void>;
}

const NavPreferencesContext = createContext<NavPreferencesValue | null>(null);

/** Load the user's sidebar menu preference once and share it (T10.12). */
export function NavPreferencesProvider({ children }: { children: ReactNode }) {
  const client = useApiClient();
  const [preference, setPreference] = useState<NavPreference | null>(null);

  useEffect(() => {
    let cancelled = false;
    client
      .getNavPreferences()
      .then((saved) => {
        if (!cancelled) setPreference({ order: saved.order, hidden: saved.hidden });
      })
      .catch(() => {
        // Fall back to the default menu; the customization screen can still save.
        if (!cancelled) setPreference({ order: [], hidden: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const save = useCallback(
    async (next: NavPreference) => {
      const saved = await client.setNavPreferences(next);
      setPreference({ order: saved.order, hidden: saved.hidden });
    },
    [client],
  );

  return (
    <NavPreferencesContext.Provider value={{ preference, save }}>{children}</NavPreferencesContext.Provider>
  );
}

export function useNavPreferences(): NavPreferencesValue {
  const ctx = useContext(NavPreferencesContext);
  if (!ctx) throw new Error("useNavPreferences must be used within a NavPreferencesProvider");
  return ctx;
}
