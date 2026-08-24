import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { getDiagnostics } from "./maintenance";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

describe("maintenance API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("rejects malformed diagnostics", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ app_version: "0.1.0" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(getDiagnostics()).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });
});
