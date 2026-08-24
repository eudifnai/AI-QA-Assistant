import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type DocumentStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";

export interface DocumentJob {
  id: string;
  status: DocumentStatus;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  sha256: string;
  size_bytes: number;
  status: DocumentStatus;
  parsed_text: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  workspace_id: string;
  name: string;
  relative_path: string;
  created_at: string;
  updated_at: string;
  latest_version: DocumentVersion;
  job: DocumentJob;
}

export type DocumentChunkSourceType = "document" | "lines" | "block" | "page";

export interface DocumentChunk {
  id: string;
  ordinal: number;
  source_type: DocumentChunkSourceType;
  source_start: number;
  source_end: number;
  start_offset: number;
  end_offset: number;
  text: string;
  locator: string;
}

export interface DocumentImportResult {
  source_path: string;
  status: "accepted" | "rejected";
  document: DocumentItem | null;
  error_code: string | null;
  error_message: string | null;
}

const statuses = new Set<DocumentStatus>([
  "pending",
  "queued",
  "running",
  "passed",
  "failed",
  "error",
  "cancelled",
  "timeout",
]);
const chunkSourceTypes = new Set<DocumentChunkSourceType>(["document", "lines", "block", "page"]);

function nullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isJob(value: unknown): value is DocumentJob {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DocumentJob>;
  return (
    typeof item.id === "string" &&
    statuses.has(item.status as DocumentStatus) &&
    typeof item.progress === "number" &&
    item.progress >= 0 &&
    item.progress <= 100 &&
    nullableString(item.error_code) &&
    nullableString(item.error_message) &&
    typeof item.created_at === "string" &&
    nullableString(item.started_at) &&
    nullableString(item.finished_at)
  );
}

function isVersion(value: unknown): value is DocumentVersion {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DocumentVersion>;
  return (
    typeof item.id === "string" &&
    typeof item.version_number === "number" &&
    typeof item.sha256 === "string" &&
    item.sha256.length === 64 &&
    typeof item.size_bytes === "number" &&
    statuses.has(item.status as DocumentStatus) &&
    nullableString(item.parsed_text) &&
    nullableString(item.error_code) &&
    nullableString(item.error_message) &&
    typeof item.created_at === "string"
  );
}

function isDocument(value: unknown): value is DocumentItem {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DocumentItem>;
  return (
    typeof item.id === "string" &&
    typeof item.workspace_id === "string" &&
    typeof item.name === "string" &&
    typeof item.relative_path === "string" &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string" &&
    isVersion(item.latest_version) &&
    isJob(item.job)
  );
}

function isChunk(value: unknown): value is DocumentChunk {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DocumentChunk>;
  return (
    typeof item.id === "string" &&
    Number.isInteger(item.ordinal) &&
    (item.ordinal ?? 0) >= 1 &&
    chunkSourceTypes.has(item.source_type as DocumentChunkSourceType) &&
    Number.isInteger(item.source_start) &&
    Number.isInteger(item.source_end) &&
    (item.source_start ?? 0) >= 1 &&
    (item.source_end ?? 0) >= (item.source_start ?? 0) &&
    Number.isInteger(item.start_offset) &&
    Number.isInteger(item.end_offset) &&
    (item.start_offset ?? -1) >= 0 &&
    (item.end_offset ?? -1) >= (item.start_offset ?? 0) &&
    typeof item.text === "string" &&
    typeof item.locator === "string"
  );
}

function isImportResult(value: unknown): value is DocumentImportResult {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DocumentImportResult>;
  if (typeof item.source_path !== "string") return false;
  if (item.status === "accepted") {
    return (
      isDocument(item.document) && item.error_code === null && item.error_message === null
    );
  }
  if (item.status === "rejected") {
    return (
      item.document === null &&
      typeof item.error_code === "string" &&
      typeof item.error_message === "string"
    );
  }
  return false;
}

function validateDocument(value: unknown): DocumentItem {
  if (!isDocument(value)) {
    throw new ApiClientError("后端文档响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateDocuments(value: unknown): DocumentItem[] {
  if (!Array.isArray(value) || !value.every(isDocument)) {
    throw new ApiClientError("后端文档列表响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateChunks(value: unknown): DocumentChunk[] {
  if (!Array.isArray(value) || !value.every(isChunk)) {
    throw new ApiClientError("后端文档引用响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateImportResults(value: unknown): DocumentImportResult[] {
  if (!Array.isArray(value) || !value.every(isImportResult)) {
    throw new ApiClientError("后端批量导入响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function listDocuments(workspaceId: string): Promise<DocumentItem[]> {
  return validateDocuments(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/documents`),
  );
}

export async function importDocument(
  workspaceId: string,
  sourcePath: string,
): Promise<DocumentItem> {
  return validateDocument(
    await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/documents`, {
      source_path: sourcePath,
    }),
  );
}

export async function importDocuments(
  workspaceId: string,
  sourcePaths: string[],
): Promise<DocumentImportResult[]> {
  return validateImportResults(
    await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/documents/batch`, {
      source_paths: sourcePaths,
    }),
  );
}

export async function cancelDocumentJob(jobId: string): Promise<DocumentItem> {
  return validateDocument(await (await client()).post<unknown>(`/api/document-jobs/${jobId}/cancel`));
}

export async function listDocumentChunks(
  workspaceId: string,
  documentId: string,
): Promise<DocumentChunk[]> {
  return validateChunks(
    await (await client()).get<unknown>(
      `/api/workspaces/${workspaceId}/documents/${documentId}/chunks`,
    ),
  );
}
