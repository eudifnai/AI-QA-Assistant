import { relative, resolve, join } from "node:path";
import { pathToFileURL } from "node:url";
import { tmpdir } from "node:os";
import { writeFile } from "node:fs/promises";

import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  net,
  protocol,
  session,
  type IpcMainInvokeEvent,
} from "electron";

import {
  resolveAcceptanceSmokePath,
  writeAcceptanceSmokeProgress,
  writeAcceptanceSmokeEvidence,
} from "./acceptance-smoke.cjs";
import { resolveWorkspaceRoot, startBackend, type BackendRuntime } from "./backend-runtime.cjs";
import { handleSquirrelStartup } from "./squirrel-startup.cjs";
import {
  GET_BACKEND_CONNECTION_CHANNEL,
  SELECT_DOCUMENT_FILE_CHANNEL,
  SELECT_DOCUMENT_FILES_CHANNEL,
  SELECT_PROTO_FILE_CHANNEL,
  SAVE_REPORT_FILE_CHANNEL,
  SELECT_WORKSPACE_DIRECTORY_CHANNEL,
} from "./desktop-bridge.cjs";
import { saveReportArtifact } from "./report-export.cjs";
import {
  APPLICATION_HOST,
  APPLICATION_PROTOCOL,
  contentSecurityPolicy,
  isTrustedRendererUrl,
} from "./security.cjs";

const SQUIRREL_STARTUP = handleSquirrelStartup(
  process.argv,
  process.execPath,
  () => app.quit(),
);
if (process.platform === "win32") {
  app.setAppUserModelId("com.squirrel.AIQAAssistant.AIQAAssistant");
}

const DEVELOPMENT_URL = app.isPackaged ? null : "http://127.0.0.1:1420";
const RENDERER_ROOT = app.isPackaged ? join(__dirname, "..", "dist") : null;
const PACKAGED_ENTRY_URL = `${APPLICATION_PROTOCOL}://${APPLICATION_HOST}/index.html`;
const PRELOAD_PATH = join(__dirname, "preload.cjs");
const ACCEPTANCE_SMOKE_PATH = resolveAcceptanceSmokePath(process.argv, tmpdir());
if (ACCEPTANCE_SMOKE_PATH !== null) {
  writeAcceptanceSmokeProgress(ACCEPTANCE_SMOKE_PATH, "starting");
}

let backendRuntime: BackendRuntime | null = null;
let mainWindow: BrowserWindow | null = null;

protocol.registerSchemesAsPrivileged([
  {
    scheme: APPLICATION_PROTOCOL,
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
  },
]);

function requireTrustedSender(event: IpcMainInvokeEvent): void {
  const senderUrl = event.senderFrame?.url ?? "";
  if (!isTrustedRendererUrl(senderUrl, DEVELOPMENT_URL, app.isPackaged)) {
    throw new Error("拒绝来自非受信渲染器的桌面请求。");
  }
}

function configureSessionSecurity(): void {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [contentSecurityPolicy(DEVELOPMENT_URL !== null)],
      },
    });
  });
}

function configurePackagedProtocol(): void {
  if (RENDERER_ROOT === null) {
    return;
  }
  protocol.handle(APPLICATION_PROTOCOL, (request) => {
    const requestUrl = new URL(request.url);
    if (requestUrl.host !== APPLICATION_HOST) {
      return new Response("Not found", { status: 404 });
    }
    const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "") || "index.html";
    const assetPath = resolve(RENDERER_ROOT, relativePath);
    const assetRelativePath = relative(resolve(RENDERER_ROOT), assetPath);
    if (assetRelativePath.startsWith("..") || assetRelativePath.includes(":")) {
      return new Response("Not found", { status: 404 });
    }
    return net.fetch(pathToFileURL(assetPath).href);
  });
}

function configureWindowNavigation(window: BrowserWindow): void {
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, navigationUrl) => {
    if (!isTrustedRendererUrl(navigationUrl, DEVELOPMENT_URL, app.isPackaged)) {
      event.preventDefault();
    }
  });
}

async function createMainWindow(): Promise<BrowserWindow> {
  const window = new BrowserWindow({
    title: "AI QA Assistant",
    width: 1080,
    height: 720,
    minWidth: 760,
    minHeight: 520,
    center: true,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      preload: PRELOAD_PATH,
    },
  });
  configureWindowNavigation(window);
  window.once("ready-to-show", () => {
    if (ACCEPTANCE_SMOKE_PATH === null) {
      window.show();
    }
  });
  window.once("closed", () => {
    if (mainWindow === window) {
      mainWindow = null;
    }
  });

  if (DEVELOPMENT_URL !== null) {
    await window.loadURL(DEVELOPMENT_URL);
  } else {
    await window.loadURL(PACKAGED_ENTRY_URL);
  }
  return window;
}

function registerDesktopHandlers(): void {
  ipcMain.handle(GET_BACKEND_CONNECTION_CHANNEL, (event) => {
    requireTrustedSender(event);
    if (backendRuntime === null) {
      throw new Error("本地后端尚未准备完成。");
    }
    return backendRuntime.connection;
  });
  ipcMain.handle(SELECT_WORKSPACE_DIRECTORY_CHANNEL, async (event) => {
    requireTrustedSender(event);
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (owner === null) {
      throw new Error("无法定位当前桌面窗口。");
    }
    const result = await dialog.showOpenDialog(owner, {
      title: "选择工作空间目录",
      buttonLabel: "选择目录",
      properties: ["openDirectory", "createDirectory"],
    });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle(SELECT_DOCUMENT_FILE_CHANNEL, async (event) => {
    requireTrustedSender(event);
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (owner === null) {
      throw new Error("无法定位当前桌面窗口。");
    }
    const result = await dialog.showOpenDialog(owner, {
      title: "选择需求文档",
      buttonLabel: "导入文档",
      properties: ["openFile"],
      filters: [
        { name: "需求文档", extensions: ["md", "txt", "docx", "pdf"] },
      ],
    });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle(SELECT_DOCUMENT_FILES_CHANNEL, async (event) => {
    requireTrustedSender(event);
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (owner === null) {
      throw new Error("无法定位当前桌面窗口。");
    }
    const result = await dialog.showOpenDialog(owner, {
      title: "选择需求文档",
      buttonLabel: "导入文档",
      properties: ["openFile", "multiSelections"],
      filters: [{ name: "需求文档", extensions: ["md", "txt", "docx", "pdf"] }],
    });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle(SELECT_PROTO_FILE_CHANNEL, async (event) => {
    requireTrustedSender(event);
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (owner === null) {
      throw new Error("无法定位当前桌面窗口。");
    }
    const result = await dialog.showOpenDialog(owner, {
      title: "选择 Proto 定义",
      buttonLabel: "导入 Proto",
      properties: ["openFile"],
      filters: [{ name: "Protocol Buffers", extensions: ["proto"] }],
    });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle(SAVE_REPORT_FILE_CHANNEL, async (event, artifact: unknown) => {
    requireTrustedSender(event);
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (owner === null) {
      throw new Error("无法定位当前桌面窗口。");
    }
    return saveReportArtifact(
      artifact,
      (options) => dialog.showSaveDialog(owner, options),
      (filePath, content) => writeFile(filePath, content, { encoding: "utf8" }),
    );
  });
}

async function startApplication(): Promise<void> {
  configureSessionSecurity();
  configurePackagedProtocol();
  if (app.isPackaged) {
    backendRuntime = await startBackend({
      packaged: true,
      resourcesPath: process.resourcesPath,
      userDataPath: app.getPath("userData"),
    });
  } else {
    const workspaceRoot = resolveWorkspaceRoot([app.getAppPath(), process.cwd(), __dirname]);
    backendRuntime = await startBackend({ packaged: false, workspaceRoot });
  }
  registerDesktopHandlers();
  mainWindow = await createMainWindow();
  if (ACCEPTANCE_SMOKE_PATH !== null) {
    const userDataPath = app.getPath("userData");
    await writeAcceptanceSmokeEvidence({
      evidencePath: ACCEPTANCE_SMOKE_PATH,
      appVersion: app.getVersion(),
      userDataPath,
      databasePath: join(userDataPath, "data", "ai_qa_assistant.db"),
      apiBaseUrl: backendRuntime.connection.baseUrl,
    });
    app.quit();
  }
}

app.on("before-quit", () => {
  backendRuntime?.stop();
  backendRuntime = null;
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (mainWindow === null && backendRuntime !== null) {
    void createMainWindow().then((window) => {
      mainWindow = window;
    });
  }
});

if (!SQUIRREL_STARTUP) {
  void app.whenReady().then(async () => {
    if (ACCEPTANCE_SMOKE_PATH !== null) {
      writeAcceptanceSmokeProgress(ACCEPTANCE_SMOKE_PATH, "electron_ready");
    }
    await startApplication();
  }).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : "桌面应用启动失败。";
    dialog.showErrorBox("AI QA Assistant 启动失败", message);
    app.quit();
  });
}
