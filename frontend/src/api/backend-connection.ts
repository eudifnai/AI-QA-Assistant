export interface BackendConnection {
  baseUrl: string;
  token: string | null;
}

function isBackendConnection(value: unknown): value is BackendConnection {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<BackendConnection>;
  if (typeof candidate.baseUrl !== "string" || typeof candidate.token !== "string") {
    return false;
  }
  try {
    const url = new URL(candidate.baseUrl);
    const port = Number(url.port);
    return (
      url.protocol === "http:" &&
      url.hostname === "127.0.0.1" &&
      Number.isInteger(port) &&
      port >= 1024 &&
      port <= 65535 &&
      candidate.token.length >= 43
    );
  } catch {
    return false;
  }
}

export async function resolveBackendConnection(): Promise<BackendConnection> {
  if (window.desktopBridge === undefined) {
    return {
      baseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765",
      token: import.meta.env.VITE_API_SESSION_TOKEN ?? null,
    };
  }

  const connection = await window.desktopBridge.getBackendConnection();
  if (!isBackendConnection(connection)) {
    throw new Error("桌面后端连接信息无效。");
  }
  return connection;
}

export async function selectWorkspaceDirectory(): Promise<string | null> {
  if (window.desktopBridge === undefined) {
    return null;
  }
  const selectedPath = await window.desktopBridge.selectWorkspaceDirectory();
  if (selectedPath !== null && typeof selectedPath !== "string") {
    throw new Error("桌面目录选择结果无效。");
  }
  return selectedPath;
}

export async function selectDocumentFile(): Promise<string | null> {
  if (window.desktopBridge === undefined) {
    return null;
  }
  const selectedPath = await window.desktopBridge.selectDocumentFile();
  if (selectedPath !== null && typeof selectedPath !== "string") {
    throw new Error("桌面文件选择结果无效。");
  }
  return selectedPath;
}

export async function selectDocumentFiles(): Promise<string[]> {
  if (window.desktopBridge === undefined) {
    return [];
  }
  const selectedPaths = await window.desktopBridge.selectDocumentFiles();
  if (
    !Array.isArray(selectedPaths) ||
    selectedPaths.length > 50 ||
    !selectedPaths.every((path) => typeof path === "string" && path.length > 0)
  ) {
    throw new Error("桌面文件多选结果无效。");
  }
  return uniquePaths(selectedPaths);
}

export async function selectProtoFile(): Promise<string | null> {
  if (window.desktopBridge === undefined) {
    return null;
  }
  const selectedPath = await window.desktopBridge.selectProtoFile();
  if (selectedPath !== null && typeof selectedPath !== "string") {
    throw new Error("桌面 Proto 文件选择结果无效。");
  }
  return selectedPath;
}

export async function resolveDroppedDocumentPaths(files: File[]): Promise<string[]> {
  const bridge = window.desktopBridge;
  if (bridge === undefined) {
    return [];
  }
  if (files.length > 50) {
    throw new Error("单次最多导入 50 个文档。");
  }
  let paths: unknown[];
  try {
    paths = files.map((file) => bridge.getPathForFile(file));
  } catch {
    throw new Error("拖入内容不是可读取的本地文件。");
  }
  if (!paths.every((path) => typeof path === "string")) {
    throw new Error("拖入的本地文件路径无效。");
  }
  return uniquePaths(paths.filter((path) => path.length > 0));
}

function uniquePaths(paths: string[]): string[] {
  const seen = new Set<string>();
  return paths.filter((path) => {
    const key = path.toLocaleLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
