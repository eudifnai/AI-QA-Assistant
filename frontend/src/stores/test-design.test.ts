import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  batchUpdateTestCases,
  generateTestCases,
  generateTestPoints,
  getTestDesign,
  reviewAnalysisIssue,
  updateTestCase,
  updateTestPoint,
  type TestDesignSnapshot,
} from "../api/test-design";
import { useTestDesignStore } from "./test-design";

vi.mock("../api/test-design", () => ({
  batchUpdateTestCases: vi.fn(),
  generateTestCases: vi.fn(),
  generateTestPoints: vi.fn(),
  getTestDesign: vi.fn(),
  reviewAnalysisIssue: vi.fn(),
  updateTestCase: vi.fn(),
  updateTestPoint: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("test design store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(generateTestPoints).mockReset();
    vi.mocked(generateTestCases).mockReset();
    vi.mocked(batchUpdateTestCases).mockReset();
    vi.mocked(getTestDesign).mockReset();
    vi.mocked(reviewAnalysisIssue).mockReset();
    vi.mocked(updateTestCase).mockReset();
    vi.mocked(updateTestPoint).mockReset();
  });

  it("ignores an old run snapshot after context changes", async () => {
    const old = deferred<TestDesignSnapshot>();
    vi.mocked(getTestDesign)
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce({
        reviews: [],
        test_points: [],
        test_cases: [],
        traceability: [],
        automation_recommendations: [],
      });
    const store = useTestDesignStore();

    const first = store.load("workspace-1", "run-1");
    await store.load("workspace-1", "run-2");
    old.resolve({
      reviews: [
        {
          id: "review-old",
          run_id: "run-1",
          issue_id: "issue-old",
          status: "accepted",
          answer: "旧结论",
          created_at: "2026-08-14T03:00:00Z",
          updated_at: "2026-08-14T03:00:00Z",
        },
      ],
      test_points: [],
      test_cases: [],
      traceability: [],
      automation_recommendations: [],
    });
    await first;

    expect(store.runId).toBe("run-2");
    expect(store.reviews).toEqual([]);
  });

  it("generates, edits and batch-confirms cases in the active context", async () => {
    const testCase = {
      id: "case-1",
      run_id: "run-1",
      source_test_point_id: "point-1",
      title: "验证退款期限",
      preconditions: ["退款服务可用"],
      priority: "P1" as const,
      tags: ["boundary"],
      automation_type: "manual" as const,
      status: "draft" as const,
      steps: [
        {
          id: "step-1",
          ordinal: 1,
          action: "提交退款",
          expected_result: "退款完成",
        },
      ],
      created_at: "2026-08-14T03:00:00Z",
      updated_at: "2026-08-14T03:00:00Z",
    };
    vi.mocked(getTestDesign)
      .mockResolvedValueOnce({
        reviews: [],
        test_points: [],
        test_cases: [],
        traceability: [],
        automation_recommendations: [],
      })
      .mockResolvedValue({
        reviews: [],
        test_points: [],
        test_cases: [],
        traceability: [
          {
            issue_id: "issue-1",
            issue_title: "退款期限不清晰",
            dimension: "clarity",
            severity: "high",
            citations: [],
            review_status: "accepted",
            review_answer: "24 小时内完成",
            test_point_id: "point-1",
            test_point_title: "验证退款期限",
            test_point_status: "confirmed",
            test_case_id: "case-1",
            test_case_title: "验证退款期限",
            test_case_status: "confirmed",
            coverage_status: "covered",
          },
        ],
        automation_recommendations: [
          {
            test_point_id: "point-1",
            recommended: true,
            suggested_type: "api",
            rule_id: "repeatable_api",
            reason: "该类型输入输出明确且可重复，建议优先采用 API 自动化。",
          },
        ],
      });
    vi.mocked(generateTestCases).mockResolvedValue([testCase]);
    vi.mocked(updateTestCase).mockResolvedValue({ ...testCase, automation_type: "api" });
    vi.mocked(batchUpdateTestCases).mockResolvedValue([
      { ...testCase, automation_type: "api", status: "confirmed" },
    ]);
    const store = useTestDesignStore();
    await store.load("workspace-1", "run-1");

    await store.generateCases("workspace-1", "run-1");
    await store.saveCase("workspace-1", "run-1", "case-1", {
      title: testCase.title,
      preconditions: testCase.preconditions,
      priority: "P1",
      tags: testCase.tags,
      automation_type: "api",
      status: "draft",
      steps: [{ action: "提交退款", expected_result: "退款完成" }],
    });
    await store.batchCases("workspace-1", "run-1", {
      test_case_ids: ["case-1"],
      status: "confirmed",
    });

    expect(store.testCases[0]?.status).toBe("confirmed");
    expect(store.testCases[0]?.automation_type).toBe("api");
    expect(store.traceability[0]?.coverage_status).toBe("covered");
    expect(store.automationRecommendations[0]?.suggested_type).toBe("api");
  });

  it("ignores a generated case response after switching runs", async () => {
    const old = deferred<Awaited<ReturnType<typeof generateTestCases>>>();
    vi.mocked(getTestDesign).mockResolvedValue({
      reviews: [],
      test_points: [],
      test_cases: [],
      traceability: [],
      automation_recommendations: [],
    });
    vi.mocked(generateTestCases).mockReturnValue(old.promise);
    const store = useTestDesignStore();
    await store.load("workspace-1", "run-1");

    const pending = store.generateCases("workspace-1", "run-1");
    await store.load("workspace-1", "run-2");
    old.resolve([
      {
        id: "case-old",
        run_id: "run-1",
        source_test_point_id: "point-old",
        title: "旧用例",
        preconditions: [],
        priority: "P2",
        tags: [],
        automation_type: "manual",
        status: "draft",
        steps: [
          {
            id: "step-old",
            ordinal: 1,
            action: "旧操作",
            expected_result: "旧结果",
          },
        ],
        created_at: "2026-08-14T03:00:00Z",
        updated_at: "2026-08-14T03:00:00Z",
      },
    ]);
    await pending;

    expect(store.runId).toBe("run-2");
    expect(store.testCases).toEqual([]);
    expect(store.generatingCases).toBe(false);
  });

  it("keeps a successful mutation when the matrix refresh fails", async () => {
    const testCase = {
      id: "case-1",
      run_id: "run-1",
      source_test_point_id: "point-1",
      title: "退款期限",
      preconditions: [],
      priority: "P1" as const,
      tags: [],
      automation_type: "manual" as const,
      status: "draft" as const,
      steps: [
        {
          id: "step-1",
          ordinal: 1,
          action: "提交退款",
          expected_result: "退款完成",
        },
      ],
      created_at: "2026-08-14T03:00:00Z",
      updated_at: "2026-08-14T03:00:00Z",
    };
    vi.mocked(getTestDesign)
      .mockResolvedValueOnce({
        reviews: [],
        test_points: [],
        test_cases: [],
        traceability: [],
        automation_recommendations: [],
      })
      .mockRejectedValueOnce(new Error("网络暂不可用"));
    vi.mocked(generateTestCases).mockResolvedValue([testCase]);
    const store = useTestDesignStore();
    await store.load("workspace-1", "run-1");

    await store.generateCases("workspace-1", "run-1");

    expect(store.testCases).toEqual([testCase]);
    expect(store.error).toContain("操作已完成，但追踪矩阵和自动化建议刷新失败");
    expect(store.error).toContain("网络暂不可用");
  });
});
