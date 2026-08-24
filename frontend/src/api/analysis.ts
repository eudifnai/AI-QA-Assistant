import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";
import type { ModelProvider } from "./settings";

export type AnalysisStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";
export type AnalysisDimension =
  | "completeness"
  | "consistency"
  | "clarity"
  | "testability"
  | "feasibility";
export type AnalysisSeverity = "low" | "medium" | "high" | "critical";

export interface AnalysisCitation {
  chunk_id: string;
  ordinal: number;
  locator: string;
  text: string;
}

export interface AnalysisScore {
  dimension: AnalysisDimension;
  score: number;
  summary: string;
}

export interface AnalysisIssue {
  id: string;
  ordinal: number;
  dimension: AnalysisDimension;
  severity: AnalysisSeverity;
  title: string;
  description: string;
  impact: string;
  suggestion: string;
  question: string;
  citations: AnalysisCitation[];
}

export interface AnalysisRun {
  id: string;
  workspace_id: string;
  document_id: string;
  version_id: string;
  provider: ModelProvider;
  model_name: string;
  base_url: string;
  input_chunk_count: number;
  input_character_count: number;
  cloud_data_confirmed_at: string | null;
  status: AnalysisStatus;
  progress: number;
  overall_score: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  scores: AnalysisScore[];
  issues: AnalysisIssue[];
}

export interface AnalysisStartInput {
  expected_version_id: string;
  expected_provider: ModelProvider;
  expected_model_name: string;
  expected_base_url: string;
  expected_input_chunk_count: number;
  expected_input_character_count: number;
  cloud_data_confirmed: boolean;
}

export const ANALYSIS_DIMENSIONS: AnalysisDimension[] = [
  "completeness",
  "consistency",
  "clarity",
  "testability",
  "feasibility",
];

const statuses = new Set<AnalysisStatus>([
  "pending",
  "queued",
  "running",
  "passed",
  "failed",
  "error",
  "cancelled",
  "timeout",
]);
const dimensions = new Set<AnalysisDimension>(ANALYSIS_DIMENSIONS);
const severities = new Set<AnalysisSeverity>(["low", "medium", "high", "critical"]);

function nullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isCitation(value: unknown): value is AnalysisCitation {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AnalysisCitation>;
  return (
    typeof item.chunk_id === "string" &&
    Number.isInteger(item.ordinal) &&
    (item.ordinal ?? 0) >= 1 &&
    typeof item.locator === "string" &&
    typeof item.text === "string"
  );
}

function isScore(value: unknown): value is AnalysisScore {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AnalysisScore>;
  return (
    dimensions.has(item.dimension as AnalysisDimension) &&
    typeof item.score === "number" &&
    item.score >= 0 &&
    item.score <= 100 &&
    typeof item.summary === "string"
  );
}

function isIssue(value: unknown): value is AnalysisIssue {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AnalysisIssue>;
  return (
    typeof item.id === "string" &&
    Number.isInteger(item.ordinal) &&
    dimensions.has(item.dimension as AnalysisDimension) &&
    severities.has(item.severity as AnalysisSeverity) &&
    typeof item.title === "string" &&
    typeof item.description === "string" &&
    typeof item.impact === "string" &&
    typeof item.suggestion === "string" &&
    typeof item.question === "string" &&
    Array.isArray(item.citations) &&
    item.citations.length > 0 &&
    item.citations.every(isCitation)
  );
}

function isRun(value: unknown): value is AnalysisRun {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AnalysisRun>;
  if (
    typeof item.id !== "string" ||
    typeof item.workspace_id !== "string" ||
    typeof item.document_id !== "string" ||
    typeof item.version_id !== "string" ||
    (item.provider !== "ollama" && item.provider !== "openai_compatible") ||
    typeof item.model_name !== "string" ||
    typeof item.base_url !== "string" ||
    !Number.isInteger(item.input_chunk_count) ||
    (item.input_chunk_count ?? -1) < 0 ||
    !Number.isInteger(item.input_character_count) ||
    (item.input_character_count ?? -1) < 0 ||
    !nullableString(item.cloud_data_confirmed_at) ||
    !statuses.has(item.status as AnalysisStatus) ||
    typeof item.progress !== "number" ||
    item.progress < 0 ||
    item.progress > 100 ||
    !(item.overall_score === null || (typeof item.overall_score === "number" && item.overall_score >= 0 && item.overall_score <= 100)) ||
    !nullableString(item.error_code) ||
    !nullableString(item.error_message) ||
    typeof item.created_at !== "string" ||
    !nullableString(item.started_at) ||
    !nullableString(item.finished_at) ||
    !Array.isArray(item.scores) ||
    !item.scores.every(isScore) ||
    !Array.isArray(item.issues) ||
    !item.issues.every(isIssue)
  ) {
    return false;
  }
  if (item.status === "passed") {
    const actual = new Set(item.scores.map((score) => score.dimension));
    return item.overall_score !== null && actual.size === 5 && ANALYSIS_DIMENSIONS.every((item) => actual.has(item));
  }
  return item.scores.length === 0 && item.issues.length === 0;
}

function validateRun(value: unknown): AnalysisRun {
  if (!isRun(value)) {
    throw new ApiClientError("后端分析响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateRuns(value: unknown): AnalysisRun[] {
  if (!Array.isArray(value) || !value.every(isRun)) {
    throw new ApiClientError("后端分析列表响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function listAnalysisRuns(
  workspaceId: string,
  documentId: string,
): Promise<AnalysisRun[]> {
  return validateRuns(
    await (await client()).get<unknown>(
      `/api/workspaces/${workspaceId}/documents/${documentId}/analysis-runs`,
    ),
  );
}

export async function startAnalysis(
  workspaceId: string,
  documentId: string,
  input: AnalysisStartInput,
): Promise<AnalysisRun> {
  return validateRun(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/documents/${documentId}/analysis-runs`,
      input,
    ),
  );
}

export async function getAnalysisRun(workspaceId: string, runId: string): Promise<AnalysisRun> {
  return validateRun(
    await (await client()).get<unknown>(`/api/workspaces/${workspaceId}/analysis-runs/${runId}`),
  );
}

export async function cancelAnalysis(workspaceId: string, runId: string): Promise<AnalysisRun> {
  return validateRun(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/cancel`,
    ),
  );
}
