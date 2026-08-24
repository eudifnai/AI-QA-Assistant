const electronZipDir = process.env.AI_QA_ELECTRON_ZIP_DIR;
const { resolveWindowsSigningConfig } = require("./electron/release-signing.cjs");

const windowsSign = resolveWindowsSigningConfig(process.env);

module.exports = {
  packagerConfig: {
    asar: true,
    extraResource: [".sidecar-dist/ai-qa-backend"],
    icon: "electron/icons/icon",
      name: "AI QA Assistant",
      executableName: "ai-qa-assistant",
      ...(electronZipDir ? { electronZipDir } : {}),
      ...(windowsSign ? { windowsSign } : {}),
  },
  rebuildConfig: {},
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      platforms: ["win32"],
      config: {
        name: "AIQAAssistant",
        setupExe: "AI-QA-Assistant-Setup.exe",
          setupIcon: "electron/icons/icon.ico",
          noMsi: true,
          ...(windowsSign ? { windowsSign } : {}),
        },
    },
  ],
};
