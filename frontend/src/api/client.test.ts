import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiClientError } from "./client";

describe("ApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns JSON from a successful response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://127.0.0.1:8765", "session-token");

    await expect(client.get<unknown>("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/health",
      expect.objectContaining({
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: "Bearer session-token",
        },
      }),
    );
  });

  it("converts an error response to a safe API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "BACKEND_UNAVAILABLE",
            message: "后端不可用。",
            trace_id: "trace-1",
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new ApiClient("http://127.0.0.1:8765");

    await expect(client.get("/health")).rejects.toEqual(
      expect.objectContaining<ApiClientError>({
        name: "ApiClientError",
        code: "BACKEND_UNAVAILABLE",
        message: "后端不可用。",
        status: 503,
        traceId: "trace-1",
      }),
    );
  });

  it("posts a JSON body with the session token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "workspace-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://127.0.0.1:8765", "session-token");

    await expect(
      client.post<unknown>("/api/workspaces", { name: "Demo", path: "C:\\qa\\demo" }),
    ).resolves.toEqual({ id: "workspace-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces",
      expect.objectContaining({
        method: "POST",
        headers: {
          Accept: "application/json",
          Authorization: "Bearer session-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: "Demo", path: "C:\\qa\\demo" }),
      }),
    );
  });
});
