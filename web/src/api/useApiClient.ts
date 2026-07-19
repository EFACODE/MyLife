import { useMemo } from "react";

import { useAuth } from "../auth/AuthContext";
import { ApiClient, apiBaseUrl } from "./client";

/** An ApiClient bound to the current auth token. */
export function useApiClient(): ApiClient {
  const { token } = useAuth();
  return useMemo(() => new ApiClient(apiBaseUrl, () => token), [token]);
}
