import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { importDocuments, listDocumentChunks, listDocuments } from "./documents";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

describe("documents API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("rejects malformed document responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([{ id: "document-1" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listDocuments("workspace-1")).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });

  it("validates stable document chunk references", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify([
            {
              id: "chunk-1",
              ordinal: 1,
              source_type: "lines",
              source_start: 1,
              source_end: 2,
              start_offset: 0,
              end_offset: 12,
              text: "# 需求\n必须退款",
              locator: "第 1-2 行",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(listDocumentChunks("workspace-1", "document-1")).resolves.toEqual([
      expect.objectContaining({ id: "chunk-1", locator: "第 1-2 行" }),
    ]);
  });

  it("submits and validates per-file batch import results", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            source_path: "C:/qa/requirements.md",
            status: "rejected",
            document: null,
            error_code: "DOCUMENT_DUPLICATE",
            error_message: "该文件内容已导入当前工作空间。",
          },
        ]),
        { status: 207, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      importDocuments("workspace-1", ["C:/qa/requirements.md"]),
    ).resolves.toEqual([expect.objectContaining({ status: "rejected" })]);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/documents/batch",
      expect.objectContaining({ body: JSON.stringify({ source_paths: ["C:/qa/requirements.md"] }) }),
    );
  });
});
