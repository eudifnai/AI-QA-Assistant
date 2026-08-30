import { createHash } from "node:crypto";
import { createReadStream, existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { readdir, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { spawn } from "node:child_process";

interface ElectronZipSearchOptions {
  version: string;
  platform: NodeJS.Platform;
  arch: string;
  expectedSha256: string;
  explicitDirectory?: string;
  cacheRoot: string;
}

export interface ForgeLaunchSpec {
  executable: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export type ForgeCommand = "package" | "make";

export type WindowsSigningMode =
  | "artifact_signing"
  | "pfx"
  | "unsigned_internal_candidate";

interface WindowsSigningModule {
  buildWindowsSigningEnvironment: (environment: NodeJS.ProcessEnv) => {
    environment: NodeJS.ProcessEnv;
    mode: WindowsSigningMode;
  };
}

export interface ReleaseMetadataOptions {
  appVersion: string;
  platform: string;
  arch: string;
  signingMode: WindowsSigningMode;
}

const moduleRequire = createRequire(__filename);
const { buildWindowsSigningEnvironment } = moduleRequire(
  resolve(__dirname, "..", "electron", "release-signing.cjs"),
) as WindowsSigningModule;

export function sidecarExecutablePath(
  frontendDirectory: string,
  platform: NodeJS.Platform = process.platform,
): string {
  return join(
    resolve(frontendDirectory),
    ".sidecar-dist",
    "ai-qa-backend",
    platform === "win32" ? "ai-qa-backend.exe" : "ai-qa-backend",
  );
}

export function electronArtifactFileName(
  version: string,
  platform: string,
  arch: string,
): string {
  const normalizedVersion = version.startsWith("v") ? version : `v${version}`;
  return `electron-${normalizedVersion}-${platform}-${arch}.zip`;
}

export function defaultElectronCacheRoot(
  platform: NodeJS.Platform,
  environment: NodeJS.ProcessEnv = process.env,
  homeDirectory = homedir(),
): string {
  if (platform === "win32") {
    const localAppData = environment.LOCALAPPDATA;
    if (!localAppData) {
      throw new Error("无法定位 Electron 下载缓存：LOCALAPPDATA 未设置。");
    }
    return join(localAppData, "electron", "Cache");
  }
  if (platform === "darwin") {
    return join(homeDirectory, "Library", "Caches", "electron");
  }
  return join(environment.XDG_CACHE_HOME ?? join(homeDirectory, ".cache"), "electron");
}

async function sha256File(filePath: string): Promise<string> {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) {
    hash.update(chunk as Buffer);
  }
  return hash.digest("hex");
}

async function findArtifacts(root: string, fileName: string): Promise<string[]> {
  const matches: string[] = [];
  let entries;
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return matches;
    }
    throw error;
  }

  for (const entry of entries) {
    const entryPath = join(root, entry.name);
    if (entry.isDirectory()) {
      matches.push(...(await findArtifacts(entryPath, fileName)));
    } else if (entry.isFile() && entry.name === fileName) {
      matches.push(entryPath);
    }
  }
  return matches;
}

export async function findVerifiedElectronZip(
  options: ElectronZipSearchOptions,
): Promise<string> {
  const fileName = electronArtifactFileName(
    options.version,
    options.platform,
    options.arch,
  );
  const candidates = options.explicitDirectory
    ? [resolve(options.explicitDirectory, fileName)]
    : await findArtifacts(options.cacheRoot, fileName);
  let existingCandidateCount = 0;

  for (const candidate of candidates) {
    try {
      const checksum = await sha256File(candidate);
      existingCandidateCount += 1;
      if (checksum === options.expectedSha256.toLowerCase()) {
        return candidate;
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        throw error;
      }
    }
  }

  if (existingCandidateCount > 0) {
    throw new Error(`Electron ZIP 校验失败：${fileName} 与官方 SHA-256 不一致。`);
  }
  throw new Error(
    `未找到 ${fileName}。请重新安装 Electron 依赖以填充下载缓存，或设置 AI_QA_ELECTRON_ZIP_DIR。`,
  );
}

export function buildForgeLaunchSpec(
  frontendDirectory: string,
  electronZipPath: string,
  forgeCliPackageJsonPath: string,
  environment: NodeJS.ProcessEnv = process.env,
  command: ForgeCommand = "package",
  skipPackage = false,
): ForgeLaunchSpec {
  const signing = buildWindowsSigningEnvironment(environment);
  return {
    executable: process.execPath,
    args: [
      join(dirname(forgeCliPackageJsonPath), "dist", "electron-forge.js"),
      command,
      ...(command === "make" && skipPackage ? ["--skip-package"] : []),
    ],
    cwd: frontendDirectory,
    env: {
      ...signing.environment,
      AI_QA_ELECTRON_ZIP_DIR: dirname(electronZipPath),
    },
  };
}

export function buildReleaseSbomLaunchSpec(
  frontendDirectory: string,
  environment: NodeJS.ProcessEnv = process.env,
): ForgeLaunchSpec {
  const projectDirectory = resolve(frontendDirectory, "..");
  const safeEnvironment = { ...environment };
  for (const name of [
    "AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE",
    "AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD",
    "AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER",
    "WINDOWS_CERTIFICATE_FILE",
    "WINDOWS_CERTIFICATE_PASSWORD",
    "WINDOWS_TIMESTAMP_SERVER",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID",
    "AI_QA_WINDOWS_SIGN_MODE",
    "AI_QA_ARTIFACT_SIGNING_ENDPOINT",
    "AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME",
    "AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME",
  ]) {
    delete safeEnvironment[name];
  }
  return {
    executable: "uv",
    args: [
      "run",
      "--project",
      projectDirectory,
      "python",
      join(projectDirectory, "scripts", "release", "generate_sbom.py"),
      "--project-root",
      projectDirectory,
      "--output",
      join(frontendDirectory, "out", "make", "ai-qa-assistant.cdx.json"),
    ],
    cwd: projectDirectory,
    env: safeEnvironment,
  };
}

async function collectReleaseFiles(
  root: string,
  excludedNames = new Set(["SHA256SUMS.txt"]),
): Promise<string[]> {
  const files: string[] = [];
  let entries;
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return files;
    }
    throw error;
  }
  for (const entry of entries) {
    const entryPath = join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectReleaseFiles(entryPath, excludedNames)));
    } else if (entry.isFile() && !excludedNames.has(entry.name)) {
      files.push(entryPath);
    }
  }
  return files;
}

async function describeReleaseFiles(
  makeDirectory: string,
  files: string[],
): Promise<Array<{ path: string; sha256: string; bytes: number }>> {
  const described = [];
  for (const filePath of files) {
    described.push({
      path: relative(makeDirectory, filePath).replaceAll("\\", "/"),
      sha256: await sha256File(filePath),
      bytes: (await stat(filePath)).size,
    });
  }
  return described.sort((left, right) => left.path.localeCompare(right.path));
}

export async function writeReleaseMetadata(
  frontendDirectory: string,
  options: ReleaseMetadataOptions,
): Promise<string> {
  const makeDirectory = resolve(frontendDirectory, "out", "make");
  const sbomPath = join(makeDirectory, "ai-qa-assistant.cdx.json");
  const sbom = JSON.parse(readFileSync(sbomPath, "utf8")) as {
    bomFormat?: string;
    specVersion?: string;
  };
  if (sbom.bomFormat !== "CycloneDX" || sbom.specVersion !== "1.6") {
    throw new Error("发布 SBOM 必须是 CycloneDX 1.6 JSON。");
  }
  const files = await collectReleaseFiles(
    makeDirectory,
    new Set(["SHA256SUMS.txt", "RELEASE-METADATA.json"]),
  );
  const artifacts = await describeReleaseFiles(makeDirectory, files);
  const metadata = {
    schema_version: 1,
    app: {
      name: "AI QA Assistant",
      version: options.appVersion,
    },
    target: {
      platform: options.platform,
      arch: options.arch,
      format: "squirrel.windows",
    },
    signing: {
      mode: options.signingMode,
      verification:
        options.signingMode !== "unsigned_internal_candidate"
          ? "required_after_build"
          : "not_applicable_internal_candidate",
    },
    sbom: {
      format: "CycloneDX",
      spec_version: "1.6",
      path: "ai-qa-assistant.cdx.json",
      sha256: await sha256File(sbomPath),
    },
    artifacts,
  };
  const metadataPath = join(makeDirectory, "RELEASE-METADATA.json");
  await writeFile(
    metadataPath,
    `${JSON.stringify(metadata, undefined, 2)}\n`,
    "utf8",
  );
  return metadataPath;
}

export async function writeReleaseChecksumManifest(
  frontendDirectory: string,
): Promise<string> {
  const makeDirectory = resolve(frontendDirectory, "out", "make");
  const artifacts = await collectReleaseFiles(makeDirectory);
  const relativeArtifacts = artifacts
    .map((artifactPath) => ({
      artifactPath,
      relativePath: relative(makeDirectory, artifactPath).replaceAll("\\", "/"),
    }))
    .sort((left, right) => left.relativePath.localeCompare(right.relativePath));
  const hasSetup = relativeArtifacts.some(({ relativePath }) =>
    relativePath.toLowerCase().endsWith("setup.exe"),
  );
  const hasNugetPackage = relativeArtifacts.some(({ relativePath }) =>
    relativePath.toLowerCase().endsWith(".nupkg"),
  );
  const hasReleases = relativeArtifacts.some(
    ({ relativePath }) => relativePath.split("/").at(-1) === "RELEASES",
  );
  const hasSbom = relativeArtifacts.some(
    ({ relativePath }) => relativePath === "ai-qa-assistant.cdx.json",
  );
  const hasReleaseMetadata = relativeArtifacts.some(
    ({ relativePath }) => relativePath === "RELEASE-METADATA.json",
  );
  if (!hasSetup || !hasNugetPackage || !hasReleases) {
    throw new Error("Squirrel 发布制品不完整：必须包含 Setup.exe、full.nupkg 和 RELEASES。");
  }
  if (!hasSbom || !hasReleaseMetadata) {
    throw new Error("发布记录不完整：必须包含 CycloneDX SBOM 和 RELEASE-METADATA.json。");
  }

  const lines: string[] = [];
  for (const artifact of relativeArtifacts) {
    lines.push(`${await sha256File(artifact.artifactPath)}  ${artifact.relativePath}`);
  }
  const manifestPath = join(makeDirectory, "SHA256SUMS.txt");
  await writeFile(manifestPath, `${lines.join("\n")}\n`, "utf8");
  return manifestPath;
}

async function runLaunchSpec(launch: ForgeLaunchSpec, label: string): Promise<void> {
  await new Promise<void>((resolvePromise, reject) => {
    const child = spawn(launch.executable, launch.args, {
      cwd: launch.cwd,
      env: launch.env,
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
          `${label} 失败（code=${String(code)}, signal=${String(signal)}）。`,
        ),
      );
    });
  });
}

async function runElectronForge(
  frontendDirectory: string,
  command: ForgeCommand,
  skipPackage = false,
): Promise<void> {
  const sidecarPath = sidecarExecutablePath(frontendDirectory);
  if (!existsSync(sidecarPath)) {
    throw new Error("未找到已构建的 Python Sidecar，请先运行 pnpm backend:sidecar。");
  }
  const electronPackage = JSON.parse(
    readFileSync(moduleRequire.resolve("electron/package.json"), "utf8"),
  ) as { version: string };
  const checksums = JSON.parse(
    readFileSync(moduleRequire.resolve("electron/checksums.json"), "utf8"),
  ) as Record<string, string>;
  const fileName = electronArtifactFileName(
    electronPackage.version,
    process.platform,
    process.arch,
  );
  const expectedSha256 = checksums[fileName];
  if (!expectedSha256) {
    throw new Error(`Electron 官方校验和中缺少 ${fileName}。`);
  }

  const electronZipPath = await findVerifiedElectronZip({
    version: electronPackage.version,
    platform: process.platform,
    arch: process.arch,
    expectedSha256,
    explicitDirectory: process.env.AI_QA_ELECTRON_ZIP_DIR,
    cacheRoot: defaultElectronCacheRoot(process.platform),
  });
  const forgeCliPackageJsonPath = moduleRequire.resolve(
    "@electron-forge/cli/package.json",
  );
  const launch = buildForgeLaunchSpec(
    resolve(frontendDirectory),
    electronZipPath,
    forgeCliPackageJsonPath,
    process.env,
    command,
    skipPackage,
  );

  console.log(`使用已校验 Electron ZIP：${electronZipPath}`);
  await runLaunchSpec(launch, `Electron Forge ${command}`);
}

export async function packageElectron(frontendDirectory: string): Promise<void> {
  await runElectronForge(frontendDirectory, "package");
}

export async function makeElectron(
  frontendDirectory: string,
  skipPackage = false,
): Promise<void> {
  await rm(resolve(frontendDirectory, "out", "make"), {
    recursive: true,
    force: true,
  });
  await runElectronForge(frontendDirectory, "make", skipPackage);
  const sbomLaunch = buildReleaseSbomLaunchSpec(frontendDirectory);
  await runLaunchSpec(sbomLaunch, "CycloneDX SBOM 生成");
  const packageJson = JSON.parse(
    readFileSync(resolve(frontendDirectory, "package.json"), "utf8"),
  ) as { version: string };
  const signing = buildWindowsSigningEnvironment(process.env);
  const metadataPath = await writeReleaseMetadata(frontendDirectory, {
    appVersion: packageJson.version,
    platform: process.platform,
    arch: process.arch,
    signingMode: signing.mode,
  });
  console.log(`已生成脱敏发布元数据：${metadataPath}`);
  const manifestPath = await writeReleaseChecksumManifest(frontendDirectory);
  console.log(`已生成发布制品 SHA-256 清单：${manifestPath}`);
}
