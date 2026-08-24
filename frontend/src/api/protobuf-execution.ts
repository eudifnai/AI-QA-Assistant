import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type ProtoExecutionStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";

export interface ProtoFieldAssertion {
  path: string;
  expected_json: string;
}

export interface ProtoFieldAssertionResult extends ProtoFieldAssertion {
  actual: string | null;
  passed: boolean;
  message: string;
}

export interface ProtoExecutionEvent {
  id: string;
  ordinal: number;
  level: "info" | "warning" | "error";
  code: string;
  message: string;
  created_at: string;
}

export interface ProtoExecutionStartInput {
  environment_id: string;
  asset_id: string;
  expected_sha256: string;
  service_name: string;
  method_name: string;
  path: string;
  headers: Record<string, string>;
  request_payload: Record<string, unknown>;
  timeout_seconds: number;
  assertions: ProtoFieldAssertion[];
}

export interface ProtoExecution {
  id: string;
  workspace_id: string;
  environment_id: string | null;
  environment_name: string;
  asset_id: string | null;
  asset_name: string;
  asset_sha256: string;
  service_name: string;
  method_name: string;
  base_url: string;
  path_template: string;
  headers_template: Record<string, string>;
  request_message_type: string;
  response_message_type: string;
  request_payload: Record<string, unknown>;
  timeout_seconds: number;
  assertions: ProtoFieldAssertion[];
  assertion_results: ProtoFieldAssertionResult[];
  status: ProtoExecutionStatus;
  progress: number;
  response_status_code: number | null;
  response_headers: Record<string, string>;
  response_payload: Record<string, unknown> | null;
  response_size_bytes: number | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  events: ProtoExecutionEvent[];
}

const statuses = new Set<ProtoExecutionStatus>([
  "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout",
]);

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringMap(value: unknown): value is Record<string, string> {
  return object(value) && Object.values(value).every((item) => typeof item === "string");
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function assertion(value: unknown): value is ProtoFieldAssertion {
  return object(value) && typeof value.path === "string" && typeof value.expected_json === "string";
}

function assertionResult(value: unknown): value is ProtoFieldAssertionResult {
  if (!assertion(value)) return false;
  const result = value as Partial<ProtoFieldAssertionResult>;
  return nullableString(result.actual) && typeof result.passed === "boolean" && typeof result.message === "string";
}

function event(value: unknown): value is ProtoExecutionEvent {
  return object(value) && typeof value.id === "string" && typeof value.ordinal === "number" &&
    ["info", "warning", "error"].includes(String(value.level)) && typeof value.code === "string" &&
    typeof value.message === "string" && typeof value.created_at === "string";
}

function execution(value: unknown): value is ProtoExecution {
  if (!object(value)) return false;
  return typeof value.id === "string" && typeof value.workspace_id === "string" &&
    nullableString(value.environment_id) && typeof value.environment_name === "string" &&
    nullableString(value.asset_id) && typeof value.asset_name === "string" &&
    typeof value.asset_sha256 === "string" && /^[0-9a-f]{64}$/.test(value.asset_sha256) &&
    typeof value.service_name === "string" && typeof value.method_name === "string" &&
    typeof value.base_url === "string" && typeof value.path_template === "string" &&
    stringMap(value.headers_template) && typeof value.request_message_type === "string" &&
    typeof value.response_message_type === "string" && object(value.request_payload) &&
    typeof value.timeout_seconds === "number" && Array.isArray(value.assertions) &&
    value.assertions.every(assertion) && Array.isArray(value.assertion_results) &&
    value.assertion_results.every(assertionResult) && statuses.has(value.status as ProtoExecutionStatus) &&
    typeof value.progress === "number" && (value.response_status_code === null || typeof value.response_status_code === "number") &&
    stringMap(value.response_headers) && (value.response_payload === null || object(value.response_payload)) &&
    (value.response_size_bytes === null || typeof value.response_size_bytes === "number") &&
    (value.duration_ms === null || typeof value.duration_ms === "number") && nullableString(value.error_code) &&
    nullableString(value.error_message) && typeof value.created_at === "string" && nullableString(value.started_at) &&
    nullableString(value.finished_at) && Array.isArray(value.events) && value.events.every(event);
}

function validateExecution(value: unknown): ProtoExecution {
  if (!execution(value)) throw new ApiClientError("后端 Protobuf 执行响应格式不正确。", { code: "INVALID_RESPONSE" });
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function startProtobufExecution(workspaceId: string, input: ProtoExecutionStartInput): Promise<ProtoExecution> {
  return validateExecution(await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/protobuf-executions`, input));
}

export async function listProtobufExecutions(workspaceId: string): Promise<ProtoExecution[]> {
  const response = await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/protobuf-executions`);
  if (!Array.isArray(response) || !response.every(execution)) {
    throw new ApiClientError("后端 Protobuf 执行列表格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return response;
}

export async function getProtobufExecution(workspaceId: string, runId: string): Promise<ProtoExecution> {
  return validateExecution(await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/protobuf-executions/${runId}`));
}

export async function cancelProtobufExecution(workspaceId: string, runId: string): Promise<ProtoExecution> {
  return validateExecution(await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/protobuf-executions/${runId}/cancel`));
}
