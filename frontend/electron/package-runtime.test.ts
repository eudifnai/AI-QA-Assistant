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
import { join } from "node:path";

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
    expect(sidecarExecutablePath("C:\\repo\\frontend", "win32")).toBe(
      "C:\\repo\\frontend\\.sidecar-dist\\ai-qa-backend\\ai-qa-backend.exe",
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
      "C:\\repo\\frontend",
      "C:\\cache\\release\\electron-v43.3.0-win32-x64.zip",
      "C:\\repo\\node_modules\\@electron-forge\\cli\\package.json",
      { CI: "1" },
    );

    expect(spec).toEqual({
      executable: process.execPath,
      args: [
        "C:\\repo\\node_modules\\@electron-forge\\cli\\dist\\electron-forge.js",
        "package",
      ],
      cwd: "C:\\repo\\frontend",
      env: {
        CI: "1",
        AI_QA_ELECTRON_ZIP_DIR: "C:\\cache\\release",
      },
    });
  });

  it("builds a Forge make launch from the verified Electron ZIP", () => {
    const spec = buildForgeLaunchSpec(
      "C:\\repo\\frontend",
      "C:\\cache\\release\\electron-v43.3.0-win32-x64.zip",
      "C:\\repo\\node_modules\\@electron-forge\\cli\\package.json",
      { CI: "1" },
      "make",
    );

    expect(spec.args.at(-1)).toBe("make");
    expect(spec.env.AI_QA_ELECTRON_ZIP_DIR).toBe("C:\\cache\\release");
  });

  it("builds an SBOM process without forwarding signing secrets", () => {
    const spec = buildReleaseSbomLaunchSpec("C:\\repo\\frontend", {
      CI: "1",
      AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD: "ai-secret",
      WINDOWS_CERTIFICATE_PASSWORD: "forge-secret",
    });

    expect(spec).toEqual({
      executable: "uv",
      args: [
        "run",
        "--project",
        "C:\\repo",
        "python",
        "C:\\repo\\scripts\\release\\generate_sbom.py",
        "--project-root",
        "C:\\repo",
        "--output",
        "C:\\repo\\frontend\\out\\make\\ai-qa-assistant.cdx.json",
      ],
      cwd: "C:\\repo",
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
