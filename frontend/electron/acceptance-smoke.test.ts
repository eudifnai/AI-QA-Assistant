// @vitest-environment node

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, win32 } from "node:path";

import { describe, expect, it } from "vitest";

import {
  resolveAcceptanceSmokePath,
  writeAcceptanceSmokeProgress,
  writeAcceptanceSmokeEvidence,
} from "./acceptance-smoke.cts";

describe("Electron installed-app acceptance smoke", () => {
  it("accepts one JSON evidence path confined to the Windows temp directory", () => {
    expect(
      resolveAcceptanceSmokePath(
        [
          "AI QA Assistant.exe",
          "--ai-qa-acceptance-smoke=C:\\Temp\\ai-qa-acceptance-run.json",
        ],
        "C:\\Temp",
        "win32",
      ),
    ).toBe("C:\\Temp\\ai-qa-acceptance-run.json");
  });

  it("accepts the packaged-app evidence path from a dedicated environment variable", () => {
    expect(
      resolveAcceptanceSmokePath(
        ["AI QA Assistant.exe"],
        "C:\\Temp",
        "win32",
        {
          AI_QA_ACCEPTANCE_SMOKE_PATH:
            "C:\\Temp\\ai-qa-acceptance-environment.json",
        },
      ),
    ).toBe("C:\\Temp\\ai-qa-acceptance-environment.json");
  });

  it.each([
    "--ai-qa-acceptance-smoke=relative.json",
    "--ai-qa-acceptance-smoke=C:\\outside\\ai-qa-acceptance-run.json",
    "--ai-qa-acceptance-smoke=C:\\Temp\\not-accepted.json",
    "--ai-qa-acceptance-smoke=C:\\Temp\\ai-qa-acceptance-run.txt",
  ])("rejects an unsafe evidence destination: %s", (argument) => {
    expect(() =>
      resolveAcceptanceSmokePath(
        ["AI QA Assistant.exe", argument],
        "C:\\Temp",
        "win32",
      ),
    ).toThrow("安装验收证据路径无效");
  });

  it("writes ready evidence only after the migrated database exists", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-acceptance-smoke-test-"));
    try {
      const databasePath = join(root, "ai_qa_assistant.db");
      const evidencePath = join(root, "ai-qa-acceptance-ready.json");
      writeFileSync(databasePath, "sqlite");

      await writeAcceptanceSmokeEvidence({
        evidencePath,
        appVersion: "0.1.0",
        userDataPath: root,
        databasePath,
        apiBaseUrl: "http://127.0.0.1:54321",
      });

      const payload = JSON.parse(readFileSync(evidencePath, "utf8")) as Record<
        string,
        unknown
      >;
      expect(payload).toMatchObject({
        status: "ready",
        app_version: "0.1.0",
        user_data_path: root,
        database_path: databasePath,
        database_bytes: 6,
        api_host: "127.0.0.1",
      });
      expect(payload).not.toHaveProperty("token");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects non-loopback API evidence", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-acceptance-smoke-test-"));
    try {
      const databasePath = join(root, "ai_qa_assistant.db");
      writeFileSync(databasePath, "sqlite");

      await expect(
        writeAcceptanceSmokeEvidence({
          evidencePath: join(root, "ai-qa-acceptance-remote.json"),
          appVersion: "0.1.0",
          userDataPath: root,
          databasePath,
          apiBaseUrl: "http://0.0.0.0:54321",
        }),
      ).rejects.toThrow("安装验收本地 API 地址无效");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("writes a token-free startup stage before Electron is ready", () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-acceptance-smoke-test-"));
    try {
      const evidencePath = join(root, "ai-qa-acceptance-starting.json");
      writeAcceptanceSmokeProgress(evidencePath, "starting");

      expect(JSON.parse(readFileSync(evidencePath, "utf8"))).toMatchObject({
        status: "starting",
      });
      expect(readFileSync(evidencePath, "utf8")).not.toContain("token");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects ready evidence when the database is missing", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-acceptance-smoke-test-"));
    try {
      await expect(
        writeAcceptanceSmokeEvidence({
          evidencePath: join(root, "ai-qa-acceptance-ready.json"),
          appVersion: "0.1.0",
          userDataPath: root,
          databasePath: join(root, "missing.db"),
          apiBaseUrl: "http://127.0.0.1:54321",
        }),
      ).rejects.toThrow("安装验收未检测到迁移后的数据库");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("normalizes Windows paths before checking confinement", () => {
    expect(
      resolveAcceptanceSmokePath(
        [
          "AI QA Assistant.exe",
          "--ai-qa-acceptance-smoke=C:\\Temp\\nested\\..\\ai-qa-acceptance-normalized.json",
        ],
        "C:\\Temp",
        "win32",
      ),
    ).toBe(
      win32.resolve("C:\\Temp\\ai-qa-acceptance-normalized.json"),
    );
  });
});
