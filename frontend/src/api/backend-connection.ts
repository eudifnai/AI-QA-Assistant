import { invoke, isTauri } from "@tauri-apps/api/core";

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
  if (!isTauri()) {
    return {
      baseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765",
      token: import.meta.env.VITE_API_SESSION_TOKEN ?? null,
    };
  }

  const connection = await invoke<unknown>("get_backend_connection");
  if (!isBackendConnection(connection)) {
    throw new Error("桌面后端连接信息无效。");
  }
  return connection;
}
