// @vitest-environment node

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildBackendLaunchSpec,
  findWorkspaceRoot,
  parseBackendStartupMessage,
} from "./backend-runtime.cts";

describe("Electron backend runtime", () => {
  it("parses a valid loopback startup handshake", () => {
    const token = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";

    expect(
      parseBackendStartupMessage(
        JSON.stringify({ type: "backend_ready", port: 54321, token }),
      ),
    ).toEqual({ baseUrl: "http://127.0.0.1:54321", token });
  });

  it.each([
    { type: "wrong", port: 54321, token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG" },
    { type: "backend_ready", port: 80, token: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG" },
    { type: "backend_ready", port: 54321, token: "short" },
  ])("rejects an invalid startup handshake", (payload) => {
    expect(() => parseBackendStartupMessage(JSON.stringify(payload))).toThrow(
      "本地后端启动信息校验失败。",
    );
  });

  it("locates the workspace from a nested Electron directory", () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-test-"));
    try {
      const nested = join(root, "frontend", ".electron");
      mkdirSync(join(root, "backend", "app"), { recursive: true });
      mkdirSync(nested, { recursive: true });
      writeFileSync(join(root, "backend", "app", "desktop.py"), "");
      writeFileSync(join(root, "pyproject.toml"), "");

      expect(findWorkspaceRoot(nested)).toBe(root);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("builds a Windows Python launch without a shell", () => {
    expect(
      buildBackendLaunchSpec({
        packaged: false,
        workspaceRoot: "C:\\repo",
        platform: "win32",
        parentHeartbeatPath: "C:\\Temp\\parent.heartbeat",
      }),
    ).toEqual({
      executable: "C:\\repo\\.venv\\Scripts\\python.exe",
      args: ["-m", "backend.app.desktop"],
      cwd: "C:\\repo",
      windowsHide: true,
      environment: {
        AI_QA_PARENT_HEARTBEAT_PATH: "C:\\Temp\\parent.heartbeat",
      },
    });
  });

  it("builds a packaged Windows Sidecar launch with app-data storage", () => {
    expect(
      buildBackendLaunchSpec({
        packaged: true,
        resourcesPath: "C:\\Program Files\\AI QA Assistant\\resources",
        userDataPath: "C:\\Users\\qa\\AppData\\Roaming\\AI QA Assistant",
        platform: "win32",
        parentHeartbeatPath: "C:\\Temp\\parent.heartbeat",
      }),
    ).toEqual({
      executable:
        "C:\\Program Files\\AI QA Assistant\\resources\\ai-qa-backend\\ai-qa-backend.exe",
      args: [],
      cwd: "C:\\Users\\qa\\AppData\\Roaming\\AI QA Assistant",
      windowsHide: true,
      environment: {
        AI_QA_DATABASE_URL:
          "sqlite:///C:/Users/qa/AppData/Roaming/AI QA Assistant/data/ai_qa_assistant.db",
        AI_QA_PARENT_HEARTBEAT_PATH: "C:\\Temp\\parent.heartbeat",
      },
    });
  });
});
