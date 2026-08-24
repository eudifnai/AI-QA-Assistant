// @vitest-environment node

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
  createDesktopBridge,
  GET_BACKEND_CONNECTION_CHANNEL,
  SELECT_DOCUMENT_FILE_CHANNEL,
  SELECT_DOCUMENT_FILES_CHANNEL,
  SELECT_PROTO_FILE_CHANNEL,
  SAVE_REPORT_FILE_CHANNEL,
  SELECT_WORKSPACE_DIRECTORY_CHANNEL,
} from "./desktop-bridge.cts";

describe("Electron preload bridge", () => {
  it("exposes only explicit request methods", async () => {
    const invoke = vi
      .fn<(channel: string) => Promise<unknown>>()
      .mockResolvedValueOnce({ baseUrl: "http://127.0.0.1:54321", token: "token" })
      .mockResolvedValueOnce("C:\\qa\\workspace")
      .mockResolvedValueOnce("C:\\qa\\workspace\\requirements.md")
      .mockResolvedValueOnce([
        "C:\\qa\\workspace\\requirements.md",
        "C:\\qa\\workspace\\rules.pdf",
      ])
      .mockResolvedValueOnce("C:\\qa\\workspace\\contracts\\echo.proto");
    invoke.mockResolvedValueOnce("C:\\qa\\reports\\payment.md");
    const getPathForFile = vi.fn().mockReturnValue("C:\\qa\\workspace\\dropped.docx");
    const bridge = createDesktopBridge(invoke, getPathForFile);

    await expect(bridge.getBackendConnection()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:54321",
      token: "token",
    });
    await expect(bridge.selectWorkspaceDirectory()).resolves.toBe("C:\\qa\\workspace");
    await expect(bridge.selectDocumentFile()).resolves.toBe(
      "C:\\qa\\workspace\\requirements.md",
    );
    await expect(bridge.selectDocumentFiles()).resolves.toEqual([
      "C:\\qa\\workspace\\requirements.md",
      "C:\\qa\\workspace\\rules.pdf",
    ]);
    await expect(bridge.selectProtoFile()).resolves.toBe(
      "C:\\qa\\workspace\\contracts\\echo.proto",
    );
    const artifact = { format: "markdown", file_name: "payment.md", content: "# report" };
    await expect(bridge.saveReportFile(artifact)).resolves.toBe(
      "C:\\qa\\reports\\payment.md",
    );
    const droppedFile = {} as File;
    expect(bridge.getPathForFile(droppedFile)).toBe("C:\\qa\\workspace\\dropped.docx");
    expect(getPathForFile).toHaveBeenCalledWith(droppedFile);
    expect(invoke.mock.calls).toEqual([
      ["desktop:get-backend-connection"],
      ["desktop:select-workspace-directory"],
      ["desktop:select-document-file"],
      ["desktop:select-document-files"],
      ["desktop:select-proto-file"],
      ["desktop:save-report-file", artifact],
    ]);
    expect(Object.keys(bridge).sort()).toEqual([
      "getBackendConnection",
      "getPathForFile",
      "saveReportFile",
      "selectDocumentFile",
      "selectDocumentFiles",
      "selectProtoFile",
      "selectWorkspaceDirectory",
    ]);
  });

  it("keeps the sandboxed preload self-contained and its channels synchronized", () => {
    const preloadSource = readFileSync(join(__dirname, "preload.cts"), "utf8");

    expect(preloadSource).not.toMatch(/from\s+["']\.\//);
    expect(preloadSource).not.toMatch(/require\(["']\.\//);
    expect(preloadSource).toContain(GET_BACKEND_CONNECTION_CHANNEL);
    expect(preloadSource).toContain(SELECT_WORKSPACE_DIRECTORY_CHANNEL);
    expect(preloadSource).toContain(SELECT_DOCUMENT_FILE_CHANNEL);
    expect(preloadSource).toContain(SELECT_DOCUMENT_FILES_CHANNEL);
    expect(preloadSource).toContain(SELECT_PROTO_FILE_CHANNEL);
    expect(preloadSource).toContain(SAVE_REPORT_FILE_CHANNEL);
  });
});
