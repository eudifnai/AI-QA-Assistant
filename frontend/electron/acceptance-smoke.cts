import { randomUUID } from "node:crypto";
import { renameSync, rmSync, writeFileSync } from "node:fs";
import { rename, rm, stat, writeFile } from "node:fs/promises";
import { posix, win32 } from "node:path";

const ACCEPTANCE_ARGUMENT_PREFIX = "--ai-qa-acceptance-smoke=";
const ACCEPTANCE_FILE_NAME = /^ai-qa-acceptance-[a-z0-9-]+\.json$/i;

type AcceptancePlatform = "win32" | "posix";

export interface AcceptanceSmokeEvidenceOptions {
  evidencePath: string;
  appVersion: string;
  userDataPath: string;
  databasePath: string;
  apiBaseUrl: string;
}

function resolveAcceptanceApiHost(apiBaseUrl: string): string {
  let url: URL;
  try {
    url = new URL(apiBaseUrl);
  } catch {
    throw new Error("安装验收本地 API 地址无效。");
  }
  const port = Number(url.port);
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    !Number.isInteger(port) ||
    port < 1024 ||
    port > 65535 ||
    url.username !== "" ||
    url.password !== "" ||
    url.pathname !== "/" ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new Error("安装验收本地 API 地址无效。");
  }
  return url.hostname;
}

export function writeAcceptanceSmokeProgress(
  evidencePath: string,
  status: "starting" | "electron_ready",
): void {
  const temporaryPath = `${evidencePath}.tmp-${process.pid}-${randomUUID()}`;
  try {
    writeFileSync(
      temporaryPath,
      `${JSON.stringify({ status, recorded_at: new Date().toISOString() })}\n`,
      { encoding: "utf8", flag: "wx" },
    );
    renameSync(temporaryPath, evidencePath);
  } catch (error: unknown) {
    rmSync(temporaryPath, { force: true });
    throw error;
  }
}

export async function writeAcceptanceSmokeFailure(
  evidencePath: string,
  message: string,
): Promise<void> {
  const temporaryPath = `${evidencePath}.tmp-${process.pid}-${randomUUID()}`;
  try {
    await writeFile(
      temporaryPath,
      `${JSON.stringify({
        status: "error",
        message,
        recorded_at: new Date().toISOString(),
      })}\n`,
      { encoding: "utf8", flag: "wx" },
    );
    await rename(temporaryPath, evidencePath);
  } catch (error: unknown) {
    await rm(temporaryPath, { force: true }).catch(() => undefined);
    throw error;
  }
}

export function resolveAcceptanceSmokePath(
  argv: string[],
  temporaryDirectory: string,
  platform: AcceptancePlatform = process.platform === "win32" ? "win32" : "posix",
  environment: Readonly<Record<string, string | undefined>> = process.env,
): string | null {
  const requestedPaths = argv
    .filter((argument) => argument.startsWith(ACCEPTANCE_ARGUMENT_PREFIX))
    .map((argument) => argument.slice(ACCEPTANCE_ARGUMENT_PREFIX.length));
  const environmentPath = environment.AI_QA_ACCEPTANCE_SMOKE_PATH;
  if (environmentPath !== undefined && environmentPath !== "") {
    requestedPaths.push(environmentPath);
  }
  if (requestedPaths.length === 0) {
    return null;
  }
  if (requestedPaths.length !== 1) {
    throw new Error("安装验收证据路径无效。");
  }

  const pathApi = platform === "win32" ? win32 : posix;
  const rawPath = requestedPaths[0] ?? "";
  try {
    if (!pathApi.isAbsolute(rawPath)) {
      throw new Error("relative path");
    }
    const temporaryRoot = pathApi.resolve(temporaryDirectory);
    const evidencePath = pathApi.resolve(rawPath);
    const relativePath = pathApi.relative(temporaryRoot, evidencePath);
    if (
      relativePath === "" ||
      relativePath.startsWith("..") ||
      pathApi.isAbsolute(relativePath) ||
      !ACCEPTANCE_FILE_NAME.test(pathApi.basename(evidencePath))
    ) {
      throw new Error("path outside temporary directory");
    }
    return evidencePath;
  } catch {
    throw new Error("安装验收证据路径无效。");
  }
}

export async function writeAcceptanceSmokeEvidence(
  options: AcceptanceSmokeEvidenceOptions,
): Promise<void> {
  const apiHost = resolveAcceptanceApiHost(options.apiBaseUrl);
  let database;
  try {
    database = await stat(options.databasePath);
  } catch {
    throw new Error("安装验收未检测到迁移后的数据库。");
  }
  if (!database.isFile() || database.size <= 0) {
    throw new Error("安装验收未检测到迁移后的数据库。");
  }

  const payload = {
    status: "ready",
    app_version: options.appVersion,
    user_data_path: options.userDataPath,
    database_path: options.databasePath,
    database_bytes: database.size,
    api_host: apiHost,
    ready_at: new Date().toISOString(),
  };
  const temporaryPath = `${options.evidencePath}.tmp-${process.pid}-${randomUUID()}`;
  try {
    await writeFile(temporaryPath, `${JSON.stringify(payload)}\n`, {
      encoding: "utf8",
      flag: "wx",
    });
    await rename(temporaryPath, options.evidencePath);
  } catch (error: unknown) {
    await rm(temporaryPath, { force: true }).catch(() => undefined);
    throw error;
  }
}
