import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./client";

function okResponse(json: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => json } as unknown as Response;
}

describe("ApiClient", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("attaches the bearer token on authenticated requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    await new ApiClient("http://api", () => "tok").request("/x");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("omits the auth header when auth is false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    await new ApiClient("http://api", () => "tok").request("/x", { auth: false });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("throws ApiError with the status on a non-2xx response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({}, 401)));
    const client = new ApiClient("http://api", () => null);

    await expect(client.request("/x")).rejects.toBeInstanceOf(ApiError);
    await expect(client.request("/x")).rejects.toMatchObject({ status: 401 });
  });

  it("login posts form-encoded credentials and returns the token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(okResponse({ access_token: "jwt", token_type: "bearer" }));
    vi.stubGlobal("fetch", fetchMock);

    const token = await new ApiClient("http://api", () => null).login("a@b.c", "pw");

    expect(token).toBe("jwt");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/auth/login");
    expect(init.body).toContain("username=a%40b.c");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/x-www-form-urlencoded",
    );
  });

  it("upload posts multipart FormData with the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ document_id: "d1" }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["hi"], "note.txt", { type: "text/plain" });

    await new ApiClient("http://api", () => "tok").upload("/documents", file);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/documents");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("fires onUnauthorized on a 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse({}, 401)));
    const onUnauthorized = vi.fn();
    const client = new ApiClient("http://api", () => "t", onUnauthorized);

    await expect(client.request("/x")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
  });
});
