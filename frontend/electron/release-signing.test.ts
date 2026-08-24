// @vitest-environment node

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

interface SigningModule {
  buildWindowsSigningEnvironment: (
    environment: NodeJS.ProcessEnv,
  ) => {
    environment: NodeJS.ProcessEnv;
    mode: "pfx" | "unsigned_internal_candidate";
  };
  resolveWindowsSigningConfig: (
    environment: NodeJS.ProcessEnv,
  ) => Record<string, unknown> | undefined;
}

const moduleRequire = createRequire(import.meta.url);
const signing = moduleRequire("./release-signing.cjs") as SigningModule;

describe("Windows release signing config", () => {
  it("keeps the internal candidate unsigned when no certificate is configured", () => {
    expect(signing.resolveWindowsSigningConfig({})).toBeUndefined();
    expect(signing.buildWindowsSigningEnvironment({ CI: "1" })).toEqual({
      environment: { CI: "1" },
      mode: "unsigned_internal_candidate",
    });
  });

  it("fails closed when the PFX path and password are incomplete", () => {
    expect(() =>
      signing.buildWindowsSigningEnvironment({
        AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE: "release.pfx",
      }),
    ).toThrow("证书路径和口令必须同时配置");
    expect(() =>
      signing.resolveWindowsSigningConfig({
        WINDOWS_CERTIFICATE_PASSWORD: "secret",
      }),
    ).toThrow("证书路径和口令必须同时配置");
  });

  it("maps a complete PFX configuration without embedding the password in Forge config", () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-signing-test-"));
    try {
      const certificatePath = join(root, "release.pfx");
      writeFileSync(certificatePath, "fixture certificate");

      const prepared = signing.buildWindowsSigningEnvironment({
        CI: "1",
        AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE: certificatePath,
        AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD: "sensitive-password",
        AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER: "https://timestamp.example.test",
      });
      expect(prepared.mode).toBe("pfx");
      expect(prepared.environment).toMatchObject({
        CI: "1",
        WINDOWS_CERTIFICATE_FILE: resolve(certificatePath),
        WINDOWS_CERTIFICATE_PASSWORD: "sensitive-password",
        WINDOWS_TIMESTAMP_SERVER: "https://timestamp.example.test/",
      });
      expect(prepared.environment).not.toHaveProperty(
        "AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD",
      );

      const config = signing.resolveWindowsSigningConfig(prepared.environment);
      expect(config).toEqual({
        certificateFile: resolve(certificatePath),
        timestampServer: "https://timestamp.example.test/",
        description: "AI QA Assistant",
        continueOnError: false,
      });
      expect(JSON.stringify(config)).not.toContain("sensitive-password");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects a missing certificate and an invalid timestamp URL", () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-signing-test-"));
    try {
      const missingPath = join(root, "missing.pfx");
      expect(() =>
        signing.resolveWindowsSigningConfig({
          WINDOWS_CERTIFICATE_FILE: missingPath,
          WINDOWS_CERTIFICATE_PASSWORD: "secret",
        }),
      ).toThrow("签名证书不存在");

      const certificatePath = join(root, "release.pfx");
      mkdirSync(root, { recursive: true });
      writeFileSync(certificatePath, "fixture certificate");
      expect(() =>
        signing.resolveWindowsSigningConfig({
          WINDOWS_CERTIFICATE_FILE: certificatePath,
          WINDOWS_CERTIFICATE_PASSWORD: "secret",
          WINDOWS_TIMESTAMP_SERVER: "file:///timestamp",
        }),
      ).toThrow("时间戳服务必须使用 HTTP 或 HTTPS");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
