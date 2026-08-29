import {
  existsSync,
  mkdirSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import { dirname, posix, resolve, win32 } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";

const DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS = 15_000;
const PACKAGED_BACKEND_STARTUP_TIMEOUT_MS = 45_000;
const MINIMUM_SESSION_TOKEN_LENGTH = 43;

export interface BackendConnection {
  baseUrl: string;
  token: string;
}

export interface BackendLaunchSpec {
  executable: string;
  args: string[];
  cwd: string;
  windowsHide: boolean;
  environment: Record<string, string>;
}

export interface BackendRuntime {
  connection: BackendConnection;
  stop: () => void;
}

interface BackendStartupPayload {
  type?: unknown;
  port?: unknown;
  token?: unknown;
}

interface BackendLaunchBase {
  platform?: NodeJS.Platform;
  parentHeartbeatPath?: string;
}

export type BackendLaunchOptions =
  | (BackendLaunchBase & {
      packaged: false;
      workspaceRoot: string;
    })
  | (BackendLaunchBase & {
      packaged: true;
      resourcesPath: string;
      userDataPath: string;
    });

export function resolveBackendStartupTimeoutMs(
  packaged: boolean,
  overrideMs?: number,
): number {
  return (
    overrideMs ??
    (packaged
      ? PACKAGED_BACKEND_STARTUP_TIMEOUT_MS
      : DEVELOPMENT_BACKEND_STARTUP_TIMEOUT_MS)
  );
}

export function parseBackendStartupMessage(line: string): BackendConnection {
  let payload: BackendStartupPayload;
  try {
    payload = JSON.parse(line) as BackendStartupPayload;
  } catch {
    throw new Error("本地后端启动信息格式无效。");
  }

  if (
    payload.type !== "backend_ready" ||
    typeof payload.port !== "number" ||
    !Number.isInteger(payload.port) ||
    payload.port < 1024 ||
    payload.port > 65535 ||
    typeof payload.token !== "string" ||
    payload.token.length < MINIMUM_SESSION_TOKEN_LENGTH
  ) {
    throw new Error("本地后端启动信息校验失败。");
  }

  return {
    baseUrl: `http://127.0.0.1:${payload.port}`,
    token: payload.token,
  };
}

export function findWorkspaceRoot(startPath: string): string | null {
  let candidate = resolve(startPath);
  while (true) {
    if (
      existsSync(resolve(candidate, "backend", "app", "desktop.py")) &&
      existsSync(resolve(candidate, "pyproject.toml"))
    ) {
      return candidate;
    }
    const parent = dirname(candidate);
    if (parent === candidate) {
      return null;
    }
    candidate = parent;
  }
}

export function resolveWorkspaceRoot(candidates: string[]): string {
  for (const candidate of candidates) {
    const workspaceRoot = findWorkspaceRoot(candidate);
    if (workspaceRoot !== null) {
      return workspaceRoot;
    }
  }
  throw new Error("无法定位本地后端项目目录。");
}

export function buildBackendLaunchSpec(
  options: BackendLaunchOptions,
): BackendLaunchSpec {
  const platform = options.platform ?? process.platform;
  const pathApi = platform === "win32" ? win32 : posix;
  const parentHeartbeatPath =
    options.parentHeartbeatPath ??
    pathApi.join(tmpdir(), `ai-qa-parent-${process.pid}-${randomUUID()}.heartbeat`);
  if (options.packaged) {
    const databasePath = pathApi.join(
      options.userDataPath,
      "data",
      "ai_qa_assistant.db",
    );
    return {
      executable: pathApi.join(
        options.resourcesPath,
        "ai-qa-backend",
        platform === "win32" ? "ai-qa-backend.exe" : "ai-qa-backend",
      ),
      args: [],
      cwd: options.userDataPath,
      windowsHide: platform === "win32",
      environment: {
        AI_QA_DATABASE_URL: `sqlite:///${databasePath.replaceAll("\\", "/")}`,
        AI_QA_PARENT_HEARTBEAT_PATH: parentHeartbeatPath,
      },
    };
  }

  const workspaceRoot = options.workspaceRoot;
  const executable =
    platform === "win32"
      ? pathApi.join(workspaceRoot, ".venv", "Scripts", "python.exe")
      : pathApi.join(workspaceRoot, ".venv", "bin", "python");
  return {
    executable,
    args: ["-m", "backend.app.desktop"],
    cwd: workspaceRoot,
    windowsHide: platform === "win32",
    environment: { AI_QA_PARENT_HEARTBEAT_PATH: parentHeartbeatPath },
  };
}

function stopChild(child: ChildProcess): void {
  if (child.exitCode === null && !child.killed) {
    child.kill();
  }
}

export async function startBackend(
  options: BackendLaunchOptions,
  timeoutMs?: number,
): Promise<BackendRuntime> {
  const startupTimeoutMs = resolveBackendStartupTimeoutMs(
    options.packaged,
    timeoutMs,
  );
  const launch = buildBackendLaunchSpec(options);
  const heartbeatPath = launch.environment.AI_QA_PARENT_HEARTBEAT_PATH;
  if (heartbeatPath === undefined) {
    throw new Error("Electron 父进程心跳路径未配置。");
  }
  if (!existsSync(launch.executable)) {
    throw new Error(
      options.packaged
        ? "内置本地后端缺失，请重新安装应用。"
        : "项目 Python 虚拟环境不存在，请先运行 uv sync。",
    );
  }

  mkdirSync(dirname(heartbeatPath), { recursive: true });
  writeFileSync(heartbeatPath, String(process.pid), { encoding: "utf8" });
  let heartbeatTimer: NodeJS.Timeout | null = null;
  const stopHeartbeat = (): void => {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    try {
      rmSync(heartbeatPath, { force: true });
    } catch (error: unknown) {
      console.error("无法清理 Electron 父进程心跳文件。", error);
    }
  };

  let child: ChildProcess;
  try {
    child = spawn(launch.executable, launch.args, {
      cwd: launch.cwd,
      env: { ...process.env, ...launch.environment },
      shell: false,
      windowsHide: launch.windowsHide,
      stdio: ["ignore", "pipe", "inherit"],
    });
  } catch {
    stopHeartbeat();
    throw new Error("无法启动本地后端进程。");
  }
  heartbeatTimer = setInterval(() => {
    try {
      const now = new Date();
      utimesSync(heartbeatPath, now, now);
    } catch (error: unknown) {
      console.error("无法更新 Electron 父进程心跳文件。", error);
      stopHeartbeat();
      stopChild(child);
    }
  }, 1_000);
  if (child.stdout === null) {
    stopHeartbeat();
    stopChild(child);
    throw new Error("无法建立本地后端安全握手通道。");
  }

  const connection = await new Promise<BackendConnection>((resolveConnection, reject) => {
    let settled = false;
    let bufferedOutput = "";

    const finish = (callback: () => void): void => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      child.removeListener("error", onError);
      child.removeListener("exit", onExit);
      callback();
    };
    const fail = (message: string): void => {
      finish(() => {
        stopHeartbeat();
        stopChild(child);
        reject(new Error(message));
      });
    };
    const onError = (): void => fail("无法启动本地后端进程。");
    const onExit = (): void => fail("本地后端在完成启动前退出。");
    const timeout = setTimeout(
      () => fail("等待本地后端启动超时。"),
      startupTimeoutMs,
    );

    child.once("error", onError);
    child.once("exit", onExit);
    child.stdout?.on("data", (chunk: Buffer) => {
      if (settled) {
        return;
      }
      bufferedOutput += chunk.toString("utf8");
      const newlineIndex = bufferedOutput.indexOf("\n");
      if (newlineIndex < 0) {
        return;
      }
      const startupLine = bufferedOutput.slice(0, newlineIndex).trim();
      try {
        const parsed = parseBackendStartupMessage(startupLine);
        finish(() => resolveConnection(parsed));
      } catch (error: unknown) {
        fail(error instanceof Error ? error.message : "本地后端启动信息无效。");
      }
    });
  });

  return {
    connection,
    stop: () => {
      stopHeartbeat();
      stopChild(child);
    },
  };
}
