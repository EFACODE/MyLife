import { useMemo } from "react";

import { useAuth } from "../auth/AuthContext";
import { ApiClient, apiBaseUrl } from "./client";

/** An ApiClient bound to the current auth token; a 401 logs the user out. */
export function useApiClient(): ApiClient {
  const { token, logout } = useAuth();
  return useMemo(
    () => new ApiClient(apiBaseUrl, () => token, logout),
    [token, logout],
  );
}
