import { afterEach, describe, expect, it, vi } from "vitest";

import {
  resolveDroppedDocumentPaths,
  resolveBackendConnection,
  selectDocumentFiles,
  selectProtoFile,
  selectWorkspaceDirectory,
} from "./backend-connection";

describe("desktop backend connection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the random backend connection through the Electron bridge", async () => {
    const getBackendConnection = vi.fn().mockResolvedValue({
      baseUrl: "http://127.0.0.1:54321",
      token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    });
    vi.stubGlobal("desktopBridge", {
      getBackendConnection,
      selectWorkspaceDirectory: vi.fn(),
    });

    await expect(resolveBackendConnection()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:54321",
      token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    });
    expect(getBackendConnection).toHaveBeenCalledOnce();
  });

  it("uses the fixed standalone development endpoint outside Electron", async () => {
    vi.stubGlobal("desktopBridge", undefined);

    await expect(resolveBackendConnection()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });

  it("delegates directory selection only when the desktop bridge is available", async () => {
    const chooseDirectory = vi.fn().mockResolvedValue("C:\\qa\\workspace");
    vi.stubGlobal("desktopBridge", {
      getBackendConnection: vi.fn(),
      selectWorkspaceDirectory: chooseDirectory,
    });

    await expect(selectWorkspaceDirectory()).resolves.toBe("C:\\qa\\workspace");
    expect(chooseDirectory).toHaveBeenCalledOnce();
  });

  it("validates multi-selection and resolves dropped files through preload", async () => {
    const chooseFiles = vi.fn().mockResolvedValue([
      "C:\\qa\\workspace\\requirements.md",
      "C:\\qa\\workspace\\rules.pdf",
    ]);
    const getPathForFile = vi
      .fn()
      .mockReturnValueOnce("C:\\qa\\workspace\\requirements.md")
      .mockReturnValueOnce("C:\\qa\\workspace\\REQUIREMENTS.md")
      .mockReturnValueOnce("");
    vi.stubGlobal("desktopBridge", {
      getBackendConnection: vi.fn(),
      selectWorkspaceDirectory: vi.fn(),
      selectDocumentFile: vi.fn(),
      selectDocumentFiles: chooseFiles,
      getPathForFile,
    });

    await expect(selectDocumentFiles()).resolves.toHaveLength(2);
    await expect(
      resolveDroppedDocumentPaths([{} as File, {} as File, {} as File]),
    ).resolves.toEqual(["C:\\qa\\workspace\\requirements.md"]);
  });

  it("selects one Proto file through the dedicated desktop bridge method", async () => {
    const chooseProto = vi.fn().mockResolvedValue("C:\\qa\\workspace\\contracts\\echo.proto");
    vi.stubGlobal("desktopBridge", {
      getBackendConnection: vi.fn(),
      selectProtoFile: chooseProto,
    });

    await expect(selectProtoFile()).resolves.toBe(
      "C:\\qa\\workspace\\contracts\\echo.proto",
    );
    expect(chooseProto).toHaveBeenCalledOnce();
  });
});
