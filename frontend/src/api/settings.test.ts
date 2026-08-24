import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { getCredentialStatus, getSettings, saveModelCredential } from "./settings";

vi.mock("./backend-connection", () => ({
  resolveBackendConnection: vi.fn(),
}));

describe("settings API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("rejects malformed settings responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ theme: "dark" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(getSettings()).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });

  it("sends a credential once and only returns configuration status", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ configured: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ configured: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await saveModelCredential("test-credential-value");
    const status = await getCredentialStatus();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8765/api/settings/model-credential",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ api_key: "test-credential-value" }),
      }),
    );
    expect(status).toEqual({ configured: true });
    expect(status).not.toHaveProperty("api_key");
  });
});
