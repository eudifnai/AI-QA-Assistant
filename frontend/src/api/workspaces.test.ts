import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { deleteWorkspace, listWorkspaces, renameWorkspace } from "./workspaces";

vi.mock("./backend-connection", () => ({
  resolveBackendConnection: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:8765",
    token: null,
  }),
}));

describe("workspace API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("rejects malformed workspace responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([{ id: "missing-fields" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listWorkspaces()).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });

  it("uses constrained HTTP methods for rename and delete", async () => {
    const workspace = {
      id: "workspace-1",
      name: "新名称",
      path: "C:\\qa\\payment",
      created_at: "2026-08-04T01:00:00Z",
      last_opened_at: "2026-08-04T02:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(workspace), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(workspace), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await renameWorkspace(workspace.id, "新名称");
    await deleteWorkspace(workspace.id);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8765/api/workspaces/workspace-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "新名称" }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8765/api/workspaces/workspace-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
