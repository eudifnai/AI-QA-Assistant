// @vitest-environment node

import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildReleaseSbomLaunchSpec,
  buildForgeLaunchSpec,
  electronArtifactFileName,
  findVerifiedElectronZip,
  sidecarExecutablePath,
  writeReleaseMetadata,
  writeReleaseChecksumManifest,
} from "./package-runtime.cts";

const VERSION = "43.3.0";
const PLATFORM = "win32";
const ARCH = "x64";
const FRONTEND_DIRECTORY = resolve("test-fixtures", "repo", "frontend");
const PROJECT_DIRECTORY = resolve(FRONTEND_DIRECTORY, "..");
const ELECTRON_ZIP_PATH = join(
  resolve("test-fixtures", "cache", "release"),
  electronArtifactFileName(VERSION, PLATFORM, ARCH),
);
const FORGE_PACKAGE_JSON_PATH = join(
  PROJECT_DIRECTORY,
  "node_modules",
  "@electron-forge",
  "cli",
  "package.json",
);

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

describe("Electron package runtime", () => {
  it("builds the official Electron artifact name", () => {
    expect(electronArtifactFileName(VERSION, PLATFORM, ARCH)).toBe(
      "electron-v43.3.0-win32-x64.zip",
    );
  });

  it("resolves the platform-specific Sidecar executable", () => {
    expect(sidecarExecutablePath(FRONTEND_DIRECTORY, "win32")).toBe(
      join(
        FRONTEND_DIRECTORY,
        ".sidecar-dist",
        "ai-qa-backend",
        "ai-qa-backend.exe",
      ),
    );
  });

  it("prefers and verifies an explicitly configured ZIP directory", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-package-test-"));
    try {
      const artifactPath = join(root, electronArtifactFileName(VERSION, PLATFORM, ARCH));
      writeFileSync(artifactPath, "verified artifact");

      await expect(
        findVerifiedElectronZip({
          version: VERSION,
          platform: PLATFORM,
          arch: ARCH,
          expectedSha256: sha256("verified artifact"),
          explicitDirectory: root,
          cacheRoot: join(root, "unused-cache"),
        }),
      ).resolves.toBe(artifactPath);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("finds a verified artifact in a nested Electron download cache", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-package-test-"));
    try {
      const cacheDirectory = join(root, "cache", "hashed-release-directory");
      mkdirSync(cacheDirectory, { recursive: true });
      const artifactPath = join(
        cacheDirectory,
        electronArtifactFileName(VERSION, PLATFORM, ARCH),
      );
      writeFileSync(artifactPath, "cached artifact");

      await expect(
        findVerifiedElectronZip({
          version: VERSION,
          platform: PLATFORM,
          arch: ARCH,
          expectedSha256: sha256("cached artifact"),
          cacheRoot: join(root, "cache"),
        }),
      ).resolves.toBe(artifactPath);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects a cached artifact whose checksum is invalid", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-package-test-"));
    try {
      const cacheDirectory = join(root, "cache", "hashed-release-directory");
      mkdirSync(cacheDirectory, { recursive: true });
      writeFileSync(
        join(cacheDirectory, electronArtifactFileName(VERSION, PLATFORM, ARCH)),
        "tampered artifact",
      );

      await expect(
        findVerifiedElectronZip({
          version: VERSION,
          platform: PLATFORM,
          arch: ARCH,
          expectedSha256: sha256("expected artifact"),
          cacheRoot: join(root, "cache"),
        }),
      ).rejects.toThrow("Electron ZIP 校验失败");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports a missing explicitly configured artifact separately", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-package-test-"));
    try {
      await expect(
        findVerifiedElectronZip({
          version: VERSION,
          platform: PLATFORM,
          arch: ARCH,
          expectedSha256: sha256("expected artifact"),
          explicitDirectory: root,
          cacheRoot: join(root, "unused-cache"),
        }),
      ).rejects.toThrow("未找到 electron-v43.3.0-win32-x64.zip");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("passes only the verified ZIP directory to Electron Forge", () => {
    const spec = buildForgeLaunchSpec(
      FRONTEND_DIRECTORY,
      ELECTRON_ZIP_PATH,
      FORGE_PACKAGE_JSON_PATH,
      { CI: "1" },
    );

    expect(spec).toEqual({
      executable: process.execPath,
      args: [
        join(dirname(FORGE_PACKAGE_JSON_PATH), "dist", "electron-forge.js"),
        "package",
      ],
      cwd: FRONTEND_DIRECTORY,
      env: {
        CI: "1",
        AI_QA_ELECTRON_ZIP_DIR: dirname(ELECTRON_ZIP_PATH),
      },
    });
  });

  it("builds a Forge make launch from the verified Electron ZIP", () => {
    const spec = buildForgeLaunchSpec(
      FRONTEND_DIRECTORY,
      ELECTRON_ZIP_PATH,
      FORGE_PACKAGE_JSON_PATH,
      { CI: "1" },
      "make",
    );

    expect(spec.args.at(-1)).toBe("make");
    expect(spec.env.AI_QA_ELECTRON_ZIP_DIR).toBe(dirname(ELECTRON_ZIP_PATH));
  });

  it("can make a signed installer from an already packaged application", () => {
    const spec = buildForgeLaunchSpec(
      FRONTEND_DIRECTORY,
      ELECTRON_ZIP_PATH,
      FORGE_PACKAGE_JSON_PATH,
      {
        CI: "1",
        AI_QA_WINDOWS_SIGN_MODE: "artifact_signing",
        AI_QA_ARTIFACT_SIGNING_ENDPOINT: "https://eus.codesigning.azure.net/",
        AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME: "ai-qa-signing",
        AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME: "public-trust",
      },
      "make",
      true,
    );

    expect(spec.args.slice(-2)).toEqual(["make", "--skip-package"]);
  });

  it("builds an SBOM process without forwarding signing secrets", () => {
    const spec = buildReleaseSbomLaunchSpec(FRONTEND_DIRECTORY, {
      CI: "1",
      AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD: "ai-secret",
      WINDOWS_CERTIFICATE_PASSWORD: "forge-secret",
      ACTIONS_ID_TOKEN_REQUEST_TOKEN: "oidc-request-token",
      ACTIONS_ID_TOKEN_REQUEST_URL: "https://oidc.example.test",
      AZURE_CLIENT_SECRET: "azure-secret",
      AZURE_CLIENT_ID: "client-id",
      AZURE_TENANT_ID: "tenant-id",
      AZURE_SUBSCRIPTION_ID: "subscription-id",
      AI_QA_WINDOWS_SIGN_MODE: "artifact_signing",
      AI_QA_ARTIFACT_SIGNING_ENDPOINT: "https://eus.codesigning.azure.net/",
      AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME: "ai-qa-signing",
      AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME: "public-trust",
    });

    expect(spec).toEqual({
      executable: "uv",
      args: [
        "run",
        "--project",
        PROJECT_DIRECTORY,
        "python",
        join(PROJECT_DIRECTORY, "scripts", "release", "generate_sbom.py"),
        "--project-root",
        PROJECT_DIRECTORY,
        "--output",
        join(FRONTEND_DIRECTORY, "out", "make", "ai-qa-assistant.cdx.json"),
      ],
      cwd: PROJECT_DIRECTORY,
      env: { CI: "1" },
    });
  });

  it("writes release metadata without certificate paths or passwords", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-release-test-"));
    try {
      const artifactDirectory = join(root, "out", "make", "squirrel.windows", "x64");
      mkdirSync(artifactDirectory, { recursive: true });
      for (const [name, content] of Object.entries({
        "AI-QA-Assistant-Setup.exe": "setup",
        "AIQAAssistant-0.1.0-full.nupkg": "package",
        RELEASES: "releases",
      })) {
        writeFileSync(join(artifactDirectory, name), content);
      }
      writeFileSync(
        join(root, "out", "make", "ai-qa-assistant.cdx.json"),
        '{"bomFormat":"CycloneDX","specVersion":"1.6"}\n',
      );

      const metadataPath = await writeReleaseMetadata(root, {
        appVersion: "0.1.0",
        platform: "win32",
        arch: "x64",
        signingMode: "pfx",
      });
      const metadataText = readFileSync(metadataPath, "utf8");
      const metadata = JSON.parse(metadataText) as {
        app: { version: string };
        artifacts: unknown[];
        signing: { mode: string; verification: string };
      };

      expect(metadata.app.version).toBe("0.1.0");
      expect(metadata.artifacts).toHaveLength(4);
      expect(metadata.signing).toEqual({
        mode: "pfx",
        verification: "required_after_build",
      });
      expect(metadataText).not.toContain("certificate");
      expect(metadataText).not.toContain("password");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("records Artifact Signing as requiring post-build verification", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-release-test-"));
    try {
      const artifactDirectory = join(root, "out", "make", "squirrel.windows", "x64");
      mkdirSync(artifactDirectory, { recursive: true });
      for (const name of [
        "AI-QA-Assistant-Setup.exe",
        "AIQAAssistant-0.1.0-full.nupkg",
        "RELEASES",
      ]) {
        writeFileSync(join(artifactDirectory, name), name);
      }
      writeFileSync(
        join(root, "out", "make", "ai-qa-assistant.cdx.json"),
        '{"bomFormat":"CycloneDX","specVersion":"1.6"}\n',
      );

      const metadataPath = await writeReleaseMetadata(root, {
        appVersion: "0.1.0",
        platform: "win32",
        arch: "x64",
        signingMode: "artifact_signing",
      });
      const metadata = JSON.parse(readFileSync(metadataPath, "utf8")) as {
        signing: { mode: string; verification: string };
      };
      expect(metadata.signing).toEqual({
        mode: "artifact_signing",
        verification: "required_after_build",
      });
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("writes a sorted SHA-256 manifest for all Squirrel artifacts", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-release-test-"));
    try {
      const artifactDirectory = join(root, "out", "make", "squirrel.windows", "x64");
      mkdirSync(artifactDirectory, { recursive: true });
      const artifacts = {
        "squirrel.windows/x64/AI-QA-Assistant-Setup.exe": "setup artifact",
        "squirrel.windows/x64/AIQAAssistant-0.1.0-full.nupkg": "nuget artifact",
        "squirrel.windows/x64/RELEASES": "release metadata",
        "ai-qa-assistant.cdx.json": "sbom",
        "RELEASE-METADATA.json": "release record",
      };
      for (const [relativePath, content] of Object.entries(artifacts)) {
        const artifactPath = join(root, "out", "make", relativePath);
        mkdirSync(join(artifactPath, ".."), { recursive: true });
        writeFileSync(artifactPath, content);
      }

      const manifestPath = await writeReleaseChecksumManifest(root);

      expect(manifestPath).toBe(join(root, "out", "make", "SHA256SUMS.txt"));
      expect(readFileSync(manifestPath, "utf8")).toBe(
        Object.entries(artifacts)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(
            ([relativePath, content]) => `${sha256(content)}  ${relativePath}`,
          )
          .join("\n") + "\n",
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects an incomplete Squirrel artifact set", async () => {
    const root = mkdtempSync(join(tmpdir(), "ai-qa-electron-release-test-"));
    try {
      const artifactDirectory = join(root, "out", "make", "squirrel.windows", "x64");
      mkdirSync(artifactDirectory, { recursive: true });
      writeFileSync(join(artifactDirectory, "AI-QA-Assistant-Setup.exe"), "setup");

      await expect(writeReleaseChecksumManifest(root)).rejects.toThrow(
        "Squirrel 发布制品不完整",
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
