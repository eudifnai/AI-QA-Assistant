import { spawn } from "node:child_process";
import { posix, win32 } from "node:path";

interface UnhandledSquirrelAction {
  handled: false;
}

interface HandledSquirrelAction {
  handled: true;
  quitImmediately: boolean;
  executable: string | null;
  args: string[];
}

export type SquirrelStartupAction =
  | UnhandledSquirrelAction
  | HandledSquirrelAction;

interface DetachedSquirrelProcess {
  once(event: "error", listener: () => void): void;
  unref(): void;
}

type SpawnSquirrelProcess = (executable: string, args: string[]) => DetachedSquirrelProcess;
type ScheduleSquirrelQuit = (callback: () => void, delayMilliseconds: number) => void;

export function buildSquirrelStartupAction(
  argv: string[],
  executablePath: string,
  platform: NodeJS.Platform = process.platform,
): SquirrelStartupAction {
  if (platform !== "win32") {
    return { handled: false };
  }
  const event = argv[1];
  if (event === "--squirrel-obsolete") {
    return {
      handled: true,
      quitImmediately: true,
      executable: null,
      args: [],
    };
  }
  const pathApi = platform === "win32" ? win32 : posix;
  const argument =
    event === "--squirrel-install" || event === "--squirrel-updated"
      ? `--createShortcut=${pathApi.basename(executablePath)}`
      : event === "--squirrel-uninstall"
        ? `--removeShortcut=${pathApi.basename(executablePath)}`
        : null;
  if (argument === null) {
    return { handled: false };
  }
  return {
    handled: true,
    quitImmediately: false,
    executable: pathApi.resolve(pathApi.dirname(executablePath), "..", "Update.exe"),
    args: [argument],
  };
}

export function handleSquirrelStartup(
  argv: string[],
  executablePath: string,
  quit: () => void,
  platform: NodeJS.Platform = process.platform,
  spawnProcess: SpawnSquirrelProcess = (executable, args) =>
    spawn(executable, args, {
      shell: false,
      detached: true,
      windowsHide: true,
      stdio: "ignore",
    }),
  scheduleQuit: ScheduleSquirrelQuit = (callback, delayMilliseconds) => {
    setTimeout(callback, delayMilliseconds);
  },
): boolean {
  const action = buildSquirrelStartupAction(argv, executablePath, platform);
  if (!action.handled) {
    return false;
  }
  if (action.quitImmediately || action.executable === null) {
    quit();
    return true;
  }

  try {
    const child = spawnProcess(action.executable, action.args);
    let settled = false;
    const finish = (): void => {
      if (!settled) {
        settled = true;
        quit();
      }
    };
    child.once("error", finish);
    child.unref();
    scheduleQuit(finish, 1000);
  } catch {
    quit();
  }
  return true;
}
