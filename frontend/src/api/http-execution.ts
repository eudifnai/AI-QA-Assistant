import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type HttpExecutionStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";
export type HttpMethod = "DELETE" | "GET" | "HEAD" | "OPTIONS" | "PATCH" | "POST" | "PUT";
export type HttpAssertionKind =
  | "status_code"
  | "header_equals"
  | "body_contains"
  | "json_path_equals";
export interface HttpAssertion {
  kind: HttpAssertionKind;
  target: string | null;
  expected: string;
}
export interface HttpAssertionResult extends HttpAssertion {
  actual: string | null;
  passed: boolean;
  message: string;
}
export interface HttpExecutionEvent {
  id: string;
  ordinal: number;
  level: "info" | "warning" | "error";
  code: string;
  message: string;
  attempt: number | null;
  created_at: string;
}

export interface HttpEnvironment {
  id: string;
  workspace_id: string;
  name: string;
  base_url: string;
  variables: Record<string, string>;
  secret_names: string[];
  created_at: string;
  updated_at: string;
}

export interface HttpEnvironmentInput {
  name: string;
  base_url: string;
  variables: Record<string, string>;
}

export interface HttpExecutionStartInput {
  environment_id: string;
  method: HttpMethod;
  path: string;
  headers: Record<string, string>;
  body: string | null;
  timeout_seconds: number;
  max_attempts: number;
  assertions: HttpAssertion[];
}

export interface HttpExecution {
  id: string;
  workspace_id: string;
  environment_id: string | null;
  environment_name: string;
  method: HttpMethod;
  base_url: string;
  path_template: string;
  headers_template: Record<string, string>;
  body_template: string | null;
  timeout_seconds: number;
  max_attempts: number;
  assertions: HttpAssertion[];
  assertion_results: HttpAssertionResult[];
  events: HttpExecutionEvent[];
  status: HttpExecutionStatus;
  progress: number;
  response_status_code: number | null;
  response_headers: Record<string, string>;
  response_body: string | null;
  response_body_encoding: "text" | "base64" | null;
  response_size_bytes: number | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

const methods = new Set<HttpMethod>(["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]);
const statuses = new Set<HttpExecutionStatus>([
  "pending",
  "queued",
  "running",
  "passed",
  "failed",
  "error",
  "cancelled",
  "timeout",
]);

function stringMap(value: unknown): value is Record<string, string> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.entries(value).every(([key, item]) => typeof key === "string" && typeof item === "string")
  );
}

function nullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isEnvironment(value: unknown): value is HttpEnvironment {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<HttpEnvironment>;
  return (
    typeof item.id === "string" &&
    typeof item.workspace_id === "string" &&
    typeof item.name === "string" &&
    typeof item.base_url === "string" &&
    stringMap(item.variables) &&
    Array.isArray(item.secret_names) &&
    item.secret_names.every((name) => typeof name === "string") &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

function isExecution(value: unknown): value is HttpExecution {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<HttpExecution>;
  return (
    typeof item.id === "string" &&
    typeof item.workspace_id === "string" &&
    nullableString(item.environment_id) &&
    typeof item.environment_name === "string" &&
    methods.has(item.method as HttpMethod) &&
    typeof item.base_url === "string" &&
    typeof item.path_template === "string" &&
    stringMap(item.headers_template) &&
    nullableString(item.body_template) &&
    typeof item.timeout_seconds === "number" &&
    typeof item.max_attempts === "number" &&
    Array.isArray(item.assertions) &&
    item.assertions.every(isAssertion) &&
    Array.isArray(item.assertion_results) &&
    item.assertion_results.every(isAssertionResult) &&
    Array.isArray(item.events) &&
    item.events.every(isEvent) &&
    statuses.has(item.status as HttpExecutionStatus) &&
    typeof item.progress === "number" &&
    (item.response_status_code === null || typeof item.response_status_code === "number") &&
    stringMap(item.response_headers) &&
    nullableString(item.response_body) &&
    (item.response_body_encoding === null ||
      item.response_body_encoding === "text" ||
      item.response_body_encoding === "base64") &&
    (item.response_size_bytes === null || typeof item.response_size_bytes === "number") &&
    (item.duration_ms === null || typeof item.duration_ms === "number") &&
    nullableString(item.error_code) &&
    nullableString(item.error_message) &&
    typeof item.created_at === "string" &&
    nullableString(item.started_at) &&
    nullableString(item.finished_at)
  );
}

function isAssertion(value: unknown): value is HttpAssertion {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<HttpAssertion>;
  return (
    ["status_code", "header_equals", "body_contains", "json_path_equals"].includes(
      item.kind ?? "",
    ) &&
    nullableString(item.target) &&
    typeof item.expected === "string"
  );
}

function isAssertionResult(value: unknown): value is HttpAssertionResult {
  if (!isAssertion(value)) return false;
  const item = value as Partial<HttpAssertionResult>;
  return (
    nullableString(item.actual) &&
    typeof item.passed === "boolean" &&
    typeof item.message === "string"
  );
}

function isEvent(value: unknown): value is HttpExecutionEvent {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<HttpExecutionEvent>;
  return (
    typeof item.id === "string" &&
    typeof item.ordinal === "number" &&
    ["info", "warning", "error"].includes(item.level ?? "") &&
    typeof item.code === "string" &&
    typeof item.message === "string" &&
    (item.attempt === null || typeof item.attempt === "number") &&
    typeof item.created_at === "string"
  );
}

function validateEnvironment(value: unknown): HttpEnvironment {
  if (!isEnvironment(value)) {
    throw new ApiClientError("后端 HTTP 环境响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateEnvironments(value: unknown): HttpEnvironment[] {
  if (!Array.isArray(value) || !value.every(isEnvironment)) {
    throw new ApiClientError("后端 HTTP 环境列表格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateExecution(value: unknown): HttpExecution {
  if (!isExecution(value)) {
    throw new ApiClientError("后端 HTTP 执行响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateExecutions(value: unknown): HttpExecution[] {
  if (!Array.isArray(value) || !value.every(isExecution)) {
    throw new ApiClientError("后端 HTTP 执行列表格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function listHttpEnvironments(workspaceId: string): Promise<HttpEnvironment[]> {
  return validateEnvironments(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/http-environments`),
  );
}

export async function createHttpEnvironment(
  workspaceId: string,
  input: HttpEnvironmentInput,
): Promise<HttpEnvironment> {
  return validateEnvironment(
    await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/http-environments`, input),
  );
}

export async function updateHttpEnvironment(
  workspaceId: string,
  environmentId: string,
  input: HttpEnvironmentInput,
): Promise<HttpEnvironment> {
  return validateEnvironment(
    await (await client()).put<unknown>(
      `/api/workspaces/${workspaceId}/http-environments/${environmentId}`,
      input,
    ),
  );
}

export async function deleteHttpEnvironment(
  workspaceId: string,
  environmentId: string,
): Promise<void> {
  await (await client()).delete<void>(
    `/api/workspaces/${workspaceId}/http-environments/${environmentId}`,
  );
}

export async function setHttpSecret(
  workspaceId: string,
  environmentId: string,
  name: string,
  secret: string,
): Promise<HttpEnvironment> {
  return validateEnvironment(
    await (await client()).put<unknown>(
      `/api/workspaces/${workspaceId}/http-environments/${environmentId}/secrets/${encodeURIComponent(name)}`,
      { secret },
    ),
  );
}

export async function deleteHttpSecret(
  workspaceId: string,
  environmentId: string,
  name: string,
): Promise<HttpEnvironment> {
  return validateEnvironment(
    await (await client()).delete<unknown>(
      `/api/workspaces/${workspaceId}/http-environments/${environmentId}/secrets/${encodeURIComponent(name)}`,
    ),
  );
}

export async function startHttpExecution(
  workspaceId: string,
  input: HttpExecutionStartInput,
): Promise<HttpExecution> {
  return validateExecution(
    await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/http-executions`, input),
  );
}

export async function listHttpExecutions(workspaceId: string): Promise<HttpExecution[]> {
  return validateExecutions(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/http-executions`),
  );
}

export async function getHttpExecution(
  workspaceId: string,
  runId: string,
): Promise<HttpExecution> {
  return validateExecution(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/http-executions/${runId}`),
  );
}

export async function cancelHttpExecution(
  workspaceId: string,
  runId: string,
): Promise<HttpExecution> {
  return validateExecution(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/http-executions/${runId}/cancel`,
    ),
  );
}

export async function rerunHttpExecution(
  workspaceId: string,
  runId: string,
): Promise<HttpExecution> {
  return validateExecution(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/http-executions/${runId}/rerun`,
    ),
  );
}
