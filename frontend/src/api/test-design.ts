import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";
import type { AnalysisCitation, AnalysisDimension, AnalysisSeverity } from "./analysis";

export type IssueReviewStatus = "accepted" | "rejected";
export type TestPointType =
  | "positive"
  | "negative"
  | "boundary"
  | "state"
  | "permission"
  | "compatibility"
  | "performance";
export type TestPointPriority = "P0" | "P1" | "P2" | "P3";
export type TestPointStatus = "draft" | "confirmed" | "disabled";
export type TestCaseAutomationType = "manual" | "api" | "web" | "mobile";
export type TestCaseStatus = "draft" | "confirmed" | "disabled";
export type TestCaseBatchStatus = "confirmed" | "disabled";
export type AutomationRuleId = "repeatable_api" | "performance_api" | "manual_context";
export type TraceabilityCoverageStatus =
  | "unreviewed"
  | "excluded"
  | "accepted"
  | "test_point"
  | "case_draft"
  | "covered"
  | "disabled";

export interface IssueReview {
  id: string;
  run_id: string;
  issue_id: string;
  status: IssueReviewStatus;
  answer: string;
  created_at: string;
  updated_at: string;
}

export interface TestPoint {
  id: string;
  run_id: string;
  source_issue_id: string;
  title: string;
  objective: string;
  test_type: TestPointType;
  priority: TestPointPriority;
  status: TestPointStatus;
  automation_candidate: boolean;
  created_at: string;
  updated_at: string;
}

export interface TestCaseStep {
  id: string;
  ordinal: number;
  action: string;
  expected_result: string;
}

export interface TestCase {
  id: string;
  run_id: string;
  source_test_point_id: string;
  title: string;
  preconditions: string[];
  priority: TestPointPriority;
  tags: string[];
  automation_type: TestCaseAutomationType;
  status: TestCaseStatus;
  steps: TestCaseStep[];
  created_at: string;
  updated_at: string;
}

export interface TraceabilityRow {
  issue_id: string;
  issue_title: string;
  dimension: AnalysisDimension;
  severity: AnalysisSeverity;
  citations: AnalysisCitation[];
  review_status: IssueReviewStatus | null;
  review_answer: string | null;
  test_point_id: string | null;
  test_point_title: string | null;
  test_point_status: TestPointStatus | null;
  test_case_id: string | null;
  test_case_title: string | null;
  test_case_status: TestCaseStatus | null;
  coverage_status: TraceabilityCoverageStatus;
}

export interface AutomationRecommendation {
  test_point_id: string;
  recommended: boolean;
  suggested_type: TestCaseAutomationType;
  rule_id: AutomationRuleId;
  reason: string;
}

export interface TestDesignSnapshot {
  reviews: IssueReview[];
  test_points: TestPoint[];
  test_cases: TestCase[];
  traceability: TraceabilityRow[];
  automation_recommendations: AutomationRecommendation[];
}

export interface IssueReviewInput {
  status: IssueReviewStatus;
  answer: string;
}

export interface TestPointUpdateInput {
  title: string;
  objective: string;
  test_type: TestPointType;
  priority: TestPointPriority;
  status: TestPointStatus;
  automation_candidate: boolean;
}

export interface TestCaseStepInput {
  action: string;
  expected_result: string;
}

export interface TestCaseUpdateInput {
  title: string;
  preconditions: string[];
  priority: TestPointPriority;
  tags: string[];
  automation_type: TestCaseAutomationType;
  status: TestCaseStatus;
  steps: TestCaseStepInput[];
}

export interface TestCaseBatchStatusInput {
  test_case_ids: string[];
  status: TestCaseBatchStatus;
}

const reviewStatuses = new Set<IssueReviewStatus>(["accepted", "rejected"]);
const pointTypes = new Set<TestPointType>([
  "positive",
  "negative",
  "boundary",
  "state",
  "permission",
  "compatibility",
  "performance",
]);
const priorities = new Set<TestPointPriority>(["P0", "P1", "P2", "P3"]);
const pointStatuses = new Set<TestPointStatus>(["draft", "confirmed", "disabled"]);
const caseAutomationTypes = new Set<TestCaseAutomationType>(["manual", "api", "web", "mobile"]);
const caseStatuses = new Set<TestCaseStatus>(["draft", "confirmed", "disabled"]);
const dimensions = new Set<AnalysisDimension>([
  "completeness",
  "consistency",
  "clarity",
  "testability",
  "feasibility",
]);
const severities = new Set<AnalysisSeverity>(["low", "medium", "high", "critical"]);
const coverageStatuses = new Set<TraceabilityCoverageStatus>([
  "unreviewed",
  "excluded",
  "accepted",
  "test_point",
  "case_draft",
  "covered",
  "disabled",
]);
const automationRuleIds = new Set<AutomationRuleId>([
  "repeatable_api",
  "performance_api",
  "manual_context",
]);

function isReview(value: unknown): value is IssueReview {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<IssueReview>;
  return (
    typeof item.id === "string" &&
    typeof item.run_id === "string" &&
    typeof item.issue_id === "string" &&
    reviewStatuses.has(item.status as IssueReviewStatus) &&
    typeof item.answer === "string" &&
    item.answer.length > 0 &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

function isPoint(value: unknown): value is TestPoint {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TestPoint>;
  return (
    typeof item.id === "string" &&
    typeof item.run_id === "string" &&
    typeof item.source_issue_id === "string" &&
    typeof item.title === "string" &&
    item.title.length > 0 &&
    typeof item.objective === "string" &&
    item.objective.length > 0 &&
    pointTypes.has(item.test_type as TestPointType) &&
    priorities.has(item.priority as TestPointPriority) &&
    pointStatuses.has(item.status as TestPointStatus) &&
    typeof item.automation_candidate === "boolean" &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

function isCaseStep(value: unknown): value is TestCaseStep {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TestCaseStep>;
  return (
    typeof item.id === "string" &&
    Number.isInteger(item.ordinal) &&
    Number(item.ordinal) >= 1 &&
    typeof item.action === "string" &&
    item.action.length > 0 &&
    typeof item.expected_result === "string" &&
    item.expected_result.length > 0
  );
}

function isCase(value: unknown): value is TestCase {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TestCase>;
  return (
    typeof item.id === "string" &&
    typeof item.run_id === "string" &&
    typeof item.source_test_point_id === "string" &&
    typeof item.title === "string" &&
    item.title.length > 0 &&
    Array.isArray(item.preconditions) &&
    item.preconditions.every((entry) => typeof entry === "string" && entry.length > 0) &&
    priorities.has(item.priority as TestPointPriority) &&
    Array.isArray(item.tags) &&
    item.tags.every((entry) => typeof entry === "string" && entry.length > 0) &&
    caseAutomationTypes.has(item.automation_type as TestCaseAutomationType) &&
    caseStatuses.has(item.status as TestCaseStatus) &&
    Array.isArray(item.steps) &&
    item.steps.length > 0 &&
    item.steps.every(isCaseStep) &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isCitation(value: unknown): value is AnalysisCitation {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AnalysisCitation>;
  return (
    typeof item.chunk_id === "string" &&
    Number.isInteger(item.ordinal) &&
    typeof item.locator === "string" &&
    typeof item.text === "string"
  );
}

function isTraceabilityRow(value: unknown): value is TraceabilityRow {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TraceabilityRow>;
  return (
    typeof item.issue_id === "string" &&
    typeof item.issue_title === "string" &&
    dimensions.has(item.dimension as AnalysisDimension) &&
    severities.has(item.severity as AnalysisSeverity) &&
    Array.isArray(item.citations) &&
    item.citations.every(isCitation) &&
    (item.review_status === null ||
      reviewStatuses.has(item.review_status as IssueReviewStatus)) &&
    isNullableString(item.review_answer) &&
    isNullableString(item.test_point_id) &&
    isNullableString(item.test_point_title) &&
    (item.test_point_status === null ||
      pointStatuses.has(item.test_point_status as TestPointStatus)) &&
    isNullableString(item.test_case_id) &&
    isNullableString(item.test_case_title) &&
    (item.test_case_status === null ||
      caseStatuses.has(item.test_case_status as TestCaseStatus)) &&
    coverageStatuses.has(item.coverage_status as TraceabilityCoverageStatus)
  );
}

function isAutomationRecommendation(value: unknown): value is AutomationRecommendation {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<AutomationRecommendation>;
  return (
    typeof item.test_point_id === "string" &&
    typeof item.recommended === "boolean" &&
    caseAutomationTypes.has(item.suggested_type as TestCaseAutomationType) &&
    automationRuleIds.has(item.rule_id as AutomationRuleId) &&
    typeof item.reason === "string" &&
    item.reason.length > 0
  );
}

function invalid(message: string): never {
  throw new ApiClientError(message, { code: "INVALID_RESPONSE" });
}

function validateReview(value: unknown): IssueReview {
  if (!isReview(value)) invalid("后端问题确认响应格式不正确。");
  return value;
}

function validatePoints(value: unknown): TestPoint[] {
  if (!Array.isArray(value) || !value.every(isPoint)) {
    invalid("后端测试点响应格式不正确。");
  }
  return value;
}

function validateCases(value: unknown): TestCase[] {
  if (!Array.isArray(value) || !value.every(isCase)) {
    invalid("后端测试用例响应格式不正确。");
  }
  return value;
}

function validateSnapshot(value: unknown): TestDesignSnapshot {
  if (typeof value !== "object" || value === null) {
    invalid("后端测试设计响应格式不正确。");
  }
  const item = value as Partial<TestDesignSnapshot>;
  if (
    !Array.isArray(item.reviews) ||
    !item.reviews.every(isReview) ||
    !Array.isArray(item.test_points) ||
    !item.test_points.every(isPoint) ||
    !Array.isArray(item.test_cases) ||
    !item.test_cases.every(isCase) ||
    !Array.isArray(item.traceability) ||
    !item.traceability.every(isTraceabilityRow) ||
    !Array.isArray(item.automation_recommendations) ||
    !item.automation_recommendations.every(isAutomationRecommendation)
  ) {
    invalid("后端测试设计响应格式不正确。");
  }
  return item as TestDesignSnapshot;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function getTestDesign(
  workspaceId: string,
  runId: string,
): Promise<TestDesignSnapshot> {
  return validateSnapshot(
    await (await client()).get<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-design`,
    ),
  );
}

export async function reviewAnalysisIssue(
  workspaceId: string,
  runId: string,
  issueId: string,
  input: IssueReviewInput,
): Promise<IssueReview> {
  return validateReview(
    await (await client()).put<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/issues/${issueId}/review`,
      input,
    ),
  );
}

export async function generateTestPoints(
  workspaceId: string,
  runId: string,
): Promise<TestPoint[]> {
  return validatePoints(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-points/generate`,
    ),
  );
}

export async function updateTestPoint(
  workspaceId: string,
  runId: string,
  pointId: string,
  input: TestPointUpdateInput,
): Promise<TestPoint> {
  const value = await (await client()).put<unknown>(
    `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-points/${pointId}`,
    input,
  );
  if (!isPoint(value)) invalid("后端测试点响应格式不正确。");
  return value;
}

export async function generateTestCases(
  workspaceId: string,
  runId: string,
): Promise<TestCase[]> {
  return validateCases(
    await (await client()).post<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-cases/generate`,
    ),
  );
}

export async function updateTestCase(
  workspaceId: string,
  runId: string,
  caseId: string,
  input: TestCaseUpdateInput,
): Promise<TestCase> {
  const value = await (await client()).put<unknown>(
    `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-cases/${caseId}`,
    input,
  );
  if (!isCase(value)) invalid("后端测试用例响应格式不正确。");
  return value;
}

export async function batchUpdateTestCases(
  workspaceId: string,
  runId: string,
  input: TestCaseBatchStatusInput,
): Promise<TestCase[]> {
  return validateCases(
    await (await client()).put<unknown>(
      `/api/workspaces/${workspaceId}/analysis-runs/${runId}/test-cases/batch-status`,
      input,
    ),
  );
}
