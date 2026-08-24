import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import {
  batchUpdateTestCases,
  generateTestCases,
  generateTestPoints,
  getTestDesign,
  reviewAnalysisIssue,
  updateTestCase,
  updateTestPoint,
} from "./test-design";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

const review = {
  id: "review-1",
  run_id: "run-1",
  issue_id: "issue-1",
  status: "accepted",
  answer: "24 小时内完成",
  created_at: "2026-08-14T03:00:00Z",
  updated_at: "2026-08-14T03:00:00Z",
};
const point = {
  id: "point-1",
  run_id: "run-1",
  source_issue_id: "issue-1",
  title: "验证退款期限",
  objective: "退款必须在 24 小时内完成。",
  test_type: "boundary",
  priority: "P1",
  status: "draft",
  automation_candidate: false,
  created_at: "2026-08-14T03:00:00Z",
  updated_at: "2026-08-14T03:00:00Z",
};
const testCase = {
  id: "case-1",
  run_id: "run-1",
  source_test_point_id: "point-1",
  title: "验证退款期限",
  preconditions: ["退款服务可用"],
  priority: "P1",
  tags: ["boundary"],
  automation_type: "manual",
  status: "draft",
  steps: [
    {
      id: "step-1",
      ordinal: 1,
      action: "提交退款申请",
      expected_result: "退款在 24 小时内完成",
    },
  ],
  created_at: "2026-08-14T03:00:00Z",
  updated_at: "2026-08-14T03:00:00Z",
};
const traceabilityRow = {
  issue_id: "issue-1",
  issue_title: "退款期限不清晰",
  dimension: "clarity",
  severity: "high",
  citations: [
    { chunk_id: "chunk-1", ordinal: 1, locator: "第 2 行", text: "必须支持退款。" },
  ],
  review_status: "accepted",
  review_answer: "24 小时内完成",
  test_point_id: "point-1",
  test_point_title: "验证退款期限",
  test_point_status: "confirmed",
  test_case_id: "case-1",
  test_case_title: "验证退款期限",
  test_case_status: "draft",
  coverage_status: "case_draft",
};
const automationRecommendation = {
  test_point_id: "point-1",
  recommended: true,
  suggested_type: "api",
  rule_id: "repeatable_api",
  reason: "该类型输入输出明确且可重复，建议优先采用 API 自动化。",
};

describe("test design API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("loads, reviews, generates and updates a traceable test point", async () => {
    const responses = [
      {
        reviews: [review],
        test_points: [point],
        test_cases: [testCase],
        traceability: [traceabilityRow],
        automation_recommendations: [automationRecommendation],
      },
      review,
      [point],
      { ...point, status: "confirmed" },
      [testCase],
      { ...testCase, automation_type: "api" },
      [{ ...testCase, status: "confirmed" }],
    ];
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(responses.shift()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getTestDesign("workspace-1", "run-1")).resolves.toEqual({
      reviews: [review],
      test_points: [point],
      test_cases: [testCase],
      traceability: [traceabilityRow],
      automation_recommendations: [automationRecommendation],
    });
    await reviewAnalysisIssue("workspace-1", "run-1", "issue-1", {
      status: "accepted",
      answer: "24 小时内完成",
    });
    await generateTestPoints("workspace-1", "run-1");
    await updateTestPoint("workspace-1", "run-1", "point-1", {
      title: point.title,
      objective: point.objective,
      test_type: "boundary",
      priority: "P1",
      status: "confirmed",
      automation_candidate: false,
    });
    await generateTestCases("workspace-1", "run-1");
    await updateTestCase("workspace-1", "run-1", "case-1", {
      title: testCase.title,
      preconditions: testCase.preconditions,
      priority: "P1",
      tags: testCase.tags,
      automation_type: "api",
      status: "draft",
      steps: testCase.steps.map(({ action, expected_result }) => ({ action, expected_result })),
    });
    await batchUpdateTestCases("workspace-1", "run-1", {
      test_case_ids: ["case-1"],
      status: "confirmed",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8765/api/workspaces/workspace-1/analysis-runs/run-1/issues/issue-1/review",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://127.0.0.1:8765/api/workspaces/workspace-1/analysis-runs/run-1/test-points/generate",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "http://127.0.0.1:8765/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/batch-status",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("rejects malformed test point enums", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            reviews: [],
            test_points: [{ ...point, priority: "urgent" }],
            test_cases: [],
            traceability: [],
            automation_recommendations: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(getTestDesign("workspace-1", "run-1")).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });

  it("rejects an unknown automation recommendation rule", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            reviews: [],
            test_points: [],
            test_cases: [],
            traceability: [],
            automation_recommendations: [
              { ...automationRecommendation, rule_id: "opaque_rule" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(getTestDesign("workspace-1", "run-1")).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });
});
