import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type WebSocketExecutionStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";

export interface WebSocketExecutionStartInput {
  environment_id: string;
  path: string;
  headers: Record<string, string>;
  message: string;
  timeout_seconds: number;
  additional_messages: string[];
  receive_count: number;
  ping_interval_seconds: number | null;
  max_reconnect_attempts: number;
  assertions: WebSocketMessageAssertion[];
}

export type WebSocketAssertionKind =
  | "encoding"
  | "text_equals"
  | "text_contains"
  | "json_path_equals";

export interface WebSocketMessageAssertion {
  message_index: number;
  kind: WebSocketAssertionKind;
  path: string | null;
  expected: string;
}

export interface WebSocketMessageAssertionResult extends WebSocketMessageAssertion {
  actual: string | null;
  passed: boolean;
  message: string;
}

export interface WebSocketMessage {
  ordinal: number;
  message: string;
  encoding: "text" | "base64";
  size_bytes: number;
}

export interface WebSocketExecutionEvent {
  id: string;
  ordinal: number;
  level: "info" | "warning" | "error";
  code: string;
  message: string;
  created_at: string;
}

export interface WebSocketExecution {
  id: string;
  workspace_id: string;
  environment_id: string | null;
  environment_name: string;
  base_url: string;
  path_template: string;
  headers_template: Record<string, string>;
  message_template: string;
  additional_message_templates: string[];
  receive_count: number;
  ping_interval_seconds: number | null;
  max_reconnect_attempts: number;
  timeout_seconds: number;
  status: WebSocketExecutionStatus;
  progress: number;
  response_message: string | null;
  response_encoding: "text" | "base64" | null;
  response_size_bytes: number | null;
  duration_ms: number | null;
  responses: WebSocketMessage[];
  assertions: WebSocketMessageAssertion[];
  assertion_results: WebSocketMessageAssertionResult[];
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  events: WebSocketExecutionEvent[];
}

const statuses = new Set<WebSocketExecutionStatus>([
  "pending",
  "queued",
  "running",
  "passed",
  "failed",
  "error",
  "cancelled",
  "timeout",
]);

function nullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function stringMap(value: unknown): value is Record<string, string> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((item) => typeof item === "string")
  );
}

function isEvent(value: unknown): value is WebSocketExecutionEvent {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<WebSocketExecutionEvent>;
  return (
    typeof item.id === "string" &&
    typeof item.ordinal === "number" &&
    ["info", "warning", "error"].includes(item.level ?? "") &&
    typeof item.code === "string" &&
    typeof item.message === "string" &&
    typeof item.created_at === "string"
  );
}

function isAssertion(value: unknown): value is WebSocketMessageAssertion {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<WebSocketMessageAssertion>;
  return (
    typeof item.message_index === "number" &&
    ["encoding", "text_equals", "text_contains", "json_path_equals"].includes(item.kind ?? "") &&
    nullableString(item.path) &&
    typeof item.expected === "string"
  );
}

function isAssertionResult(value: unknown): value is WebSocketMessageAssertionResult {
  if (!isAssertion(value)) return false;
  const item = value as Partial<WebSocketMessageAssertionResult>;
  return nullableString(item.actual) && typeof item.passed === "boolean" && typeof item.message === "string";
}

function isMessage(value: unknown): value is WebSocketMessage {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<WebSocketMessage>;
  return typeof item.ordinal === "number" && typeof item.message === "string" &&
    ["text", "base64"].includes(item.encoding ?? "") && typeof item.size_bytes === "number";
}

function isExecution(value: unknown): value is WebSocketExecution {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<WebSocketExecution>;
  return (
    typeof item.id === "string" &&
    typeof item.workspace_id === "string" &&
    nullableString(item.environment_id) &&
    typeof item.environment_name === "string" &&
    typeof item.base_url === "string" &&
    typeof item.path_template === "string" &&
    stringMap(item.headers_template) &&
    typeof item.message_template === "string" &&
    Array.isArray(item.additional_message_templates) &&
    item.additional_message_templates.every((message) => typeof message === "string") &&
    typeof item.receive_count === "number" &&
    (item.ping_interval_seconds === null || typeof item.ping_interval_seconds === "number") &&
    typeof item.max_reconnect_attempts === "number" &&
    typeof item.timeout_seconds === "number" &&
    statuses.has(item.status as WebSocketExecutionStatus) &&
    typeof item.progress === "number" &&
    nullableString(item.response_message) &&
    (item.response_encoding === null ||
      item.response_encoding === "text" ||
      item.response_encoding === "base64") &&
    (item.response_size_bytes === null || typeof item.response_size_bytes === "number") &&
    (item.duration_ms === null || typeof item.duration_ms === "number") &&
    Array.isArray(item.responses) && item.responses.every(isMessage) &&
    Array.isArray(item.assertions) && item.assertions.every(isAssertion) &&
    Array.isArray(item.assertion_results) && item.assertion_results.every(isAssertionResult) &&
    typeof item.attempt_count === "number" &&
    nullableString(item.error_code) &&
    nullableString(item.error_message) &&
    typeof item.created_at === "string" &&
    nullableString(item.started_at) &&
    nullableString(item.finished_at) &&
    Array.isArray(item.events) &&
    item.events.every(isEvent)
  );
}

function validateExecution(value: unknown): WebSocketExecution {
  if (!isExecution(value)) {
    throw new ApiClientError("后端 WebSocket 执行响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return value;
}

function validateExecutions(value: unknown): WebSocketExecution[] {
  if (!Array.isArray(value) || !value.every(isExecution)) {
    throw new ApiClientError("后端 WebSocket 执行列表格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function startWebSocketExecution(
  workspaceId: string,
  input: WebSocketExecutionStartInput,
): Promise<WebSocketExecution> {
  return validateExecution(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/websocket-executions`,
      input,
    ),
  );
}

export async function listWebSocketExecutions(
  workspaceId: string,
): Promise<WebSocketExecution[]> {
  return validateExecutions(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/websocket-executions`),
  );
}

export async function getWebSocketExecution(
  workspaceId: string,
  runId: string,
): Promise<WebSocketExecution> {
  return validateExecution(
    await (await client()).get<unknown>(
      `/api/workspaces/${workspaceId}/websocket-executions/${runId}`,
    ),
  );
}

export async function cancelWebSocketExecution(
  workspaceId: string,
  runId: string,
): Promise<WebSocketExecution> {
  return validateExecution(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/websocket-executions/${runId}/cancel`,
    ),
  );
}
