import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAsync } from "./useAsync";

describe("useAsync", () => {
  it("runs immediately and exposes ready data", async () => {
    const { result } = renderHook(() => useAsync(() => Promise.resolve(42), []));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toBe(42);
  });

  it("captures errors with the message", async () => {
    const { result } = renderHook(() => useAsync(() => Promise.reject(new Error("nope")), []));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("nope");
  });

  it("stays idle until run() when immediate is false", async () => {
    const fn = vi.fn().mockResolvedValue("x");
    const { result } = renderHook(() => useAsync(fn, [], { immediate: false }));
    expect(result.current.status).toBe("idle");
    expect(fn).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.run();
    });
    expect(result.current.status).toBe("ready");
    expect(result.current.data).toBe("x");
  });
});
