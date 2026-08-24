import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export interface BackupInfo {
  file_name: string;
  path: string;
  created_at: string;
  size_bytes: number;
}

export interface DiagnosticsReport {
  app_version: string;
  python_version: string;
  platform: string;
  api_host: string;
  database_path: string;
  backup_directory: string;
  database_size_bytes: number;
  database_integrity: string;
  database_revision: string | null;
  workspace_count: number;
  backup_count: number;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isBackupInfo(value: unknown): value is BackupInfo {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<BackupInfo>;
  return (
    typeof candidate.file_name === "string" &&
    typeof candidate.path === "string" &&
    typeof candidate.created_at === "string" &&
    isNonNegativeNumber(candidate.size_bytes)
  );
}

function validateBackup(value: unknown): BackupInfo {
  if (!isBackupInfo(value)) {
    throw new ApiClientError("后端备份响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateBackups(value: unknown): BackupInfo[] {
  if (!Array.isArray(value) || !value.every(isBackupInfo)) {
    throw new ApiClientError("后端备份列表响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return value;
}

function validateDiagnostics(value: unknown): DiagnosticsReport {
  if (typeof value !== "object" || value === null) {
    throw new ApiClientError("后端诊断响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  const candidate = value as Partial<DiagnosticsReport>;
  const valid =
    typeof candidate.app_version === "string" &&
    typeof candidate.python_version === "string" &&
    typeof candidate.platform === "string" &&
    candidate.api_host === "127.0.0.1" &&
    typeof candidate.database_path === "string" &&
    typeof candidate.backup_directory === "string" &&
    isNonNegativeNumber(candidate.database_size_bytes) &&
    typeof candidate.database_integrity === "string" &&
    (candidate.database_revision === null || typeof candidate.database_revision === "string") &&
    isNonNegativeNumber(candidate.workspace_count) &&
    isNonNegativeNumber(candidate.backup_count);
  if (!valid) {
    throw new ApiClientError("后端诊断响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return candidate as DiagnosticsReport;
}

async function maintenanceClient(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function getDiagnostics(): Promise<DiagnosticsReport> {
  const client = await maintenanceClient();
  return validateDiagnostics(await client.get<unknown>("/api/diagnostics"));
}

export async function listBackups(): Promise<BackupInfo[]> {
  const client = await maintenanceClient();
  return validateBackups(await client.get<unknown>("/api/backups"));
}

export async function createBackup(): Promise<BackupInfo> {
  const client = await maintenanceClient();
  return validateBackup(await client.post<unknown>("/api/backups"));
}
