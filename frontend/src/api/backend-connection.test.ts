import { invoke, isTauri } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: vi.fn(),
}));

describe("resolveBackendConnection", () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset();
    vi.mocked(isTauri).mockReset();
  });

  it("loads the random backend connection through Tauri IPC", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({
      baseUrl: "http://127.0.0.1:54321",
      token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    });

    await expect(resolveBackendConnection()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:54321",
      token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    });
    expect(invoke).toHaveBeenCalledWith("get_backend_connection");
  });

  it("uses the fixed standalone development endpoint outside Tauri", async () => {
    vi.mocked(isTauri).mockReturnValue(false);

    await expect(resolveBackendConnection()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
    expect(invoke).not.toHaveBeenCalled();
  });
});
