import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncStatus = "idle" | "loading" | "ready" | "error";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: string | null;
}

export interface AsyncResult<T> extends AsyncState<T> {
  /** (Re-)invoke the async function. */
  run: () => Promise<T | undefined>;
}

/**
 * Run an async function and expose a {status, data, error} state machine, so
 * pages don't hand-roll loading/ready/error handling. Re-runs when `deps` change
 * (unless `immediate` is false — then it only runs on `run()`).
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  options: { immediate?: boolean } = {},
): AsyncResult<T> {
  const immediate = options.immediate !== false;
  const [state, setState] = useState<AsyncState<T>>({
    status: immediate ? "loading" : "idle",
    data: null,
    error: null,
  });

  // Keep the latest fn without making `run` change identity every render.
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async () => {
    setState((prev) => ({ ...prev, status: "loading", error: null }));
    try {
      const data = await fnRef.current();
      setState({ status: "ready", data, error: null });
      return data;
    } catch (error) {
      setState({
        status: "error",
        data: null,
        error: error instanceof Error ? error.message : "Something went wrong.",
      });
      return undefined;
    }
  }, []);

  useEffect(() => {
    if (immediate) void run();
    // Re-run when the caller's dependencies change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, run, ...deps]);

  return { ...state, run };
}
