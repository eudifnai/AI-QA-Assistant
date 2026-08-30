const { spawn } = require("node:child_process");
const { existsSync } = require("node:fs");
const { extname, resolve } = require("node:path");

const SIGNABLE_EXTENSIONS = new Set([".dll", ".exe", ".node"]);

function buildArtifactSigningLaunchSpec(filePath) {
  const resolvedFilePath = resolve(filePath);
  if (!existsSync(resolvedFilePath)) {
    throw new Error(`Artifact Signing 候选文件不存在：${resolvedFilePath}`);
  }
  if (!SIGNABLE_EXTENSIONS.has(extname(resolvedFilePath).toLowerCase())) {
    throw new Error(`Artifact Signing 不支持该文件类型：${resolvedFilePath}`);
  }
  return {
    executable: "pwsh",
    args: [
      "-NoProfile",
      "-NonInteractive",
      "-File",
      require.resolve("./invoke-artifact-signing.ps1"),
      "-FilePath",
      resolvedFilePath,
    ],
  };
}

async function signWithArtifactSigning(filePath) {
  const launch = buildArtifactSigningLaunchSpec(filePath);
  await new Promise((resolvePromise, reject) => {
    const child = spawn(launch.executable, launch.args, {
      env: process.env,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      reject(
        new Error(
          `Artifact Signing 失败（code=${String(code)}, signal=${String(signal)}）。`,
        ),
      );
    });
  });
}

module.exports = signWithArtifactSigning;
module.exports.buildArtifactSigningLaunchSpec = buildArtifactSigningLaunchSpec;
