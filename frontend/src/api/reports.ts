import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type ReportFormat = "json" | "markdown" | "html";
export type FailureCategory = "product" | "environment" | "data" | "script" | "unknown";

export interface ReportEvent {
  level: string;
  code: string;
  message: string;
  created_at: string;
}

export interface ReportExecution {
  execution_type: "http" | "websocket" | "protobuf";
  id: string;
  name: string;
  status: string;
  duration_ms: number | null;
  request_summary: string;
  response_summary: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  events: ReportEvent[];
}

export interface ReportTrendPoint {
  date: string;
  passed: number;
  failed: number;
  error: number;
  cancelled: number;
  timeout: number;
  terminal: number;
  evaluated: number;
  pass_rate: number;
  average_duration_ms: number | null;
}

export interface FailureAttribution {
  execution_type: "http" | "websocket" | "protobuf";
  execution_id: string;
  execution_name: string;
  status: string;
  error_code: string | null;
  category: FailureCategory;
  rule_id: string;
  reason: string;
}

export interface ReportSnapshot {
  schema_version: 2;
  workspace_id: string;
  workspace_name: string;
  generated_at: string;
  execution_summary: {
    total: number;
    passed: number;
    failed: number;
    error: number;
    cancelled: number;
    timeout: number;
    active: number;
    terminal: number;
    evaluated: number;
    pass_rate: number;
    average_duration_ms: number | null;
  };
  analysis_summary: {
    total: number;
    passed: number;
    failed_or_error: number;
    latest_overall_score: number | null;
    issue_count: number;
  };
  design_summary: {
    test_point_total: number;
    test_point_confirmed: number;
    test_case_total: number;
    test_case_confirmed: number;
  };
  trend: ReportTrendPoint[];
  failure_attribution_summary: {
    total: number;
    product: number;
    environment: number;
    data: number;
    script: number;
    unknown: number;
  };
  failure_attributions: FailureAttribution[];
  slow_executions: ReportExecution[];
  executions: ReportExecution[];
}

export interface ReportArtifact {
  format: ReportFormat;
  file_name: string;
  media_type: string;
  content: string;
  generated_at: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNonNegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isNullableNonNegative(value: unknown): value is number | null {
  return value === null || isNonNegative(value);
}

function isDate(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isUtcDay(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isEvent(value: unknown): value is ReportEvent {
  return (
    isObject(value) &&
    typeof value.level === "string" &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    isDate(value.created_at)
  );
}

function isExecution(value: unknown): value is ReportExecution {
  return (
    isObject(value) &&
    (value.execution_type === "http" || value.execution_type === "websocket" || value.execution_type === "protobuf") &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.status === "string" &&
    isNullableNonNegative(value.duration_ms) &&
    typeof value.request_summary === "string" &&
    isNullableString(value.response_summary) &&
    isNullableString(value.error_code) &&
    isNullableString(value.error_message) &&
    isDate(value.created_at) &&
    (value.finished_at === null || isDate(value.finished_at)) &&
    Array.isArray(value.events) &&
    value.events.every(isEvent)
  );
}

function isTrendPoint(value: unknown): value is ReportTrendPoint {
  if (!isObject(value)) return false;
  const countKeys = [
    "passed",
    "failed",
    "error",
    "cancelled",
    "timeout",
    "terminal",
    "evaluated",
  ];
  return (
    isUtcDay(value.date) &&
    countKeys.every((key) => isNonNegative(value[key])) &&
    isNonNegative(value.pass_rate) &&
    value.pass_rate <= 100 &&
    isNullableNonNegative(value.average_duration_ms)
  );
}

function isFailureAttribution(value: unknown): value is FailureAttribution {
  return (
    isObject(value) &&
    (value.execution_type === "http" ||
      value.execution_type === "websocket" ||
      value.execution_type === "protobuf") &&
    typeof value.execution_id === "string" &&
    typeof value.execution_name === "string" &&
    typeof value.status === "string" &&
    isNullableString(value.error_code) &&
    ["product", "environment", "data", "script", "unknown"].includes(
      value.category as string,
    ) &&
    typeof value.rule_id === "string" &&
    value.rule_id.startsWith("ATTR_") &&
    typeof value.reason === "string" &&
    value.reason.length > 0
  );
}

function validateSnapshot(value: unknown): ReportSnapshot {
  if (
    !isObject(value) ||
    !isObject(value.execution_summary) ||
    !isObject(value.analysis_summary) ||
    !isObject(value.design_summary) ||
    !isObject(value.failure_attribution_summary)
  ) {
    throw new ApiClientError("后端报告响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  const execution = value.execution_summary;
  const analysis = value.analysis_summary;
  const design = value.design_summary;
  const attribution = value.failure_attribution_summary;
  const executionNumbers = [
    "total",
    "passed",
    "failed",
    "error",
    "cancelled",
    "timeout",
    "active",
    "terminal",
    "evaluated",
  ];
  const attributionNumbers = ["total", "product", "environment", "data", "script", "unknown"];
  const valid =
    value.schema_version === 2 &&
    typeof value.workspace_id === "string" &&
    typeof value.workspace_name === "string" &&
    isDate(value.generated_at) &&
    executionNumbers.every((key) => isNonNegative(execution[key])) &&
    isNonNegative(execution.pass_rate) &&
    execution.pass_rate <= 100 &&
    isNullableNonNegative(execution.average_duration_ms) &&
    ["total", "passed", "failed_or_error", "issue_count"].every((key) => isNonNegative(analysis[key])) &&
    isNullableNonNegative(analysis.latest_overall_score) &&
    (analysis.latest_overall_score === null || analysis.latest_overall_score <= 100) &&
    ["test_point_total", "test_point_confirmed", "test_case_total", "test_case_confirmed"].every((key) => isNonNegative(design[key])) &&
    Array.isArray(value.trend) &&
    value.trend.length === 14 &&
    value.trend.every(isTrendPoint) &&
    attributionNumbers.every((key) => isNonNegative(attribution[key])) &&
    attribution.total ===
      attributionNumbers
        .slice(1)
        .reduce((total, key) => total + Number(attribution[key]), 0) &&
    Array.isArray(value.failure_attributions) &&
    value.failure_attributions.every(isFailureAttribution) &&
    value.failure_attributions.length === attribution.total &&
    Array.isArray(value.slow_executions) &&
    value.slow_executions.every(isExecution) &&
    Array.isArray(value.executions) &&
    value.executions.every(isExecution);
  if (!valid) {
    throw new ApiClientError("后端报告响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value as unknown as ReportSnapshot;
}

function validateArtifact(value: unknown, expectedFormat: ReportFormat): ReportArtifact {
  const extensions = { json: ".json", markdown: ".md", html: ".html" } as const;
  const mediaTypes = { json: "application/json", markdown: "text/markdown", html: "text/html" } as const;
  const valid =
    isObject(value) &&
    value.format === expectedFormat &&
    typeof value.file_name === "string" &&
    value.file_name.toLowerCase().endsWith(extensions[expectedFormat]) &&
    value.media_type === mediaTypes[expectedFormat] &&
    typeof value.content === "string" &&
    value.content.length > 0 &&
    isDate(value.generated_at);
  if (!valid) {
    throw new ApiClientError("后端报告文件响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value as unknown as ReportArtifact;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function getReport(workspaceId: string): Promise<ReportSnapshot> {
  const api = await client();
  return validateSnapshot(await api.get<unknown>(`/api/workspaces/${encodeURIComponent(workspaceId)}/report`));
}

export async function renderReport(workspaceId: string, format: ReportFormat): Promise<ReportArtifact> {
  const api = await client();
  return validateArtifact(
    await api.post<unknown>(`/api/workspaces/${encodeURIComponent(workspaceId)}/report/render`, { format }),
    format,
  );
}
