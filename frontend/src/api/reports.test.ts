import { beforeEach, describe, expect, it, vi } from "vitest";

import { getReport, renderReport } from "./reports";

const { resolveBackendConnection } = vi.hoisted(() => ({ resolveBackendConnection: vi.fn() }));
vi.mock("./backend-connection", () => ({ resolveBackendConnection }));

const snapshot = {
  schema_version: 2,
  workspace_id: "workspace-1",
  workspace_name: "支付项目",
  generated_at: "2026-08-16T12:00:00Z",
  execution_summary: {
    total: 2,
    passed: 1,
    failed: 1,
    error: 0,
    cancelled: 0,
    timeout: 0,
    active: 0,
    terminal: 2,
    evaluated: 2,
    pass_rate: 50,
    average_duration_ms: 120,
  },
  analysis_summary: {
    total: 1,
    passed: 1,
    failed_or_error: 0,
    latest_overall_score: 88,
    issue_count: 3,
  },
  design_summary: {
    test_point_total: 3,
    test_point_confirmed: 2,
    test_case_total: 2,
    test_case_confirmed: 1,
  },
  trend: Array.from({ length: 14 }, (_, index) => ({
    date: `2026-08-${String(index + 3).padStart(2, "0")}`,
    passed: 0,
    failed: 0,
    error: 0,
    cancelled: 0,
    timeout: 0,
    terminal: 0,
    evaluated: 0,
    pass_rate: 0,
    average_duration_ms: null,
  })),
  failure_attribution_summary: {
    total: 1,
    product: 1,
    environment: 0,
    data: 0,
    script: 0,
    unknown: 0,
  },
  failure_attributions: [
    {
      execution_type: "http",
      execution_id: "run-2",
      execution_name: "支付失败",
      status: "failed",
      error_code: "HTTP_ASSERTION_FAILED",
      category: "product",
      rule_id: "ATTR_PRODUCT_ASSERTION",
      reason: "断言未满足，初步归为产品行为差异。",
    },
  ],
  slow_executions: [],
  executions: [],
};

describe("reports api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    resolveBackendConnection.mockResolvedValue({
      baseUrl: "http://127.0.0.1:54321",
      token: "session-token",
    });
  });

  it("loads and renders a workspace-scoped report", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            format: "markdown",
            file_name: "payment.md",
            media_type: "text/markdown",
            content: "# report\n",
            generated_at: "2026-08-16T12:00:00Z",
          }),
          { status: 200 },
        ),
      );

    await expect(getReport("workspace-1")).resolves.toEqual(snapshot);
    await expect(renderReport("workspace-1", "markdown")).resolves.toMatchObject({
      file_name: "payment.md",
      content: "# report\n",
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:54321/api/workspaces/workspace-1/report",
    );
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ format: "markdown" }),
    });
  });

  it("rejects malformed snapshots and artifacts", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...snapshot, execution_summary: { total: -1 } }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            format: "html",
            file_name: "wrong.exe",
            media_type: "text/html",
            content: "safe",
            generated_at: "2026-08-16T12:00:00Z",
          }),
          { status: 200 },
        ),
      );

    await expect(getReport("workspace-1")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
    await expect(renderReport("workspace-1", "html")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });

  it("rejects malformed trend and attribution data", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...snapshot, trend: snapshot.trend.slice(1) }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...snapshot,
            failure_attributions: [
              { ...snapshot.failure_attributions[0], category: "model_guess" },
            ],
          }),
          { status: 200 },
        ),
      );

    await expect(getReport("workspace-1")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
    await expect(getReport("workspace-1")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });
});
