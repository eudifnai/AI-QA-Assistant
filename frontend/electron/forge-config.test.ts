// @vitest-environment node

import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

interface ForgeMakerConfig {
  name: string;
  platforms?: string[];
  config?: Record<string, unknown>;
}

interface ForgeConfig {
  packagerConfig: Record<string, unknown>;
  makers: ForgeMakerConfig[];
}

const moduleRequire = createRequire(import.meta.url);

describe("Electron Forge release config", () => {
  it("builds an unsigned Windows Squirrel installer with stable artifact names", () => {
    const config = moduleRequire("../forge.config.cjs") as ForgeConfig;

    expect(config.makers).toEqual([
      {
        name: "@electron-forge/maker-squirrel",
        platforms: ["win32"],
        config: {
          name: "AIQAAssistant",
          setupExe: "AI-QA-Assistant-Setup.exe",
          setupIcon: "electron/icons/icon.ico",
          noMsi: true,
        },
      },
    ]);
    expect(JSON.stringify(config.makers)).not.toContain("certificatePassword");
    expect(config.packagerConfig).not.toHaveProperty("windowsSign");
  });

  it("does not rely on a hoisted Squirrel runtime dependency", () => {
    const packageJson = moduleRequire("../package.json") as {
      dependencies?: Record<string, string>;
    };

    expect(packageJson.dependencies ?? {}).not.toHaveProperty(
      "electron-squirrel-startup",
    );
  });
});
