import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { getReport, renderReport } from "../api/reports";
import { useWorkspaceStore } from "../stores/workspaces";
import ReportsView from "./ReportsView.vue";

vi.mock("../api/reports", () => ({ getReport: vi.fn(), renderReport: vi.fn() }));

describe("ReportsView", () => {
  it("shows deterministic statistics and exports through the desktop bridge", async () => {
    vi.mocked(getReport).mockResolvedValue({
      schema_version: 2,
      workspace_id: "workspace-1",
      workspace_name: "支付项目",
      generated_at: "2026-08-16T12:00:00Z",
      execution_summary: { total: 2, passed: 1, failed: 1, error: 0, cancelled: 0, timeout: 0, active: 0, terminal: 2, evaluated: 2, pass_rate: 50, average_duration_ms: 120 },
      analysis_summary: { total: 1, passed: 1, failed_or_error: 0, latest_overall_score: 88, issue_count: 3 },
      design_summary: { test_point_total: 3, test_point_confirmed: 2, test_case_total: 2, test_case_confirmed: 1 },
      trend: Array.from({ length: 14 }, (_, index) => ({
        date: `2026-08-${String(index + 3).padStart(2, "0")}`,
        passed: index === 13 ? 1 : 0,
        failed: 0,
        error: 0,
        cancelled: 0,
        timeout: 0,
        terminal: index === 13 ? 1 : 0,
        evaluated: index === 13 ? 1 : 0,
        pass_rate: index === 13 ? 100 : 0,
        average_duration_ms: index === 13 ? 120 : null,
      })),
      failure_attribution_summary: { total: 1, product: 1, environment: 0, data: 0, script: 0, unknown: 0 },
      failure_attributions: [{
        execution_type: "http",
        execution_id: "run-2",
        execution_name: "支付失败",
        status: "failed",
        error_code: "HTTP_ASSERTION_FAILED",
        category: "product",
        rule_id: "ATTR_PRODUCT_ASSERTION",
        reason: "断言未满足，初步归为产品行为差异。",
      }],
      slow_executions: [],
      executions: [],
    });
    vi.mocked(renderReport).mockResolvedValue({
      format: "json",
      file_name: "payment.json",
      media_type: "application/json",
      content: "{}",
      generated_at: "2026-08-16T12:00:00Z",
    });
    const saveReportFile = vi.fn().mockResolvedValue("C:\\qa\\payment.json");
    Object.defineProperty(window, "desktopBridge", {
      configurable: true,
      value: { saveReportFile },
    });
    const pinia = createPinia();
    const workspaceStore = useWorkspaceStore(pinia);
    workspaceStore.activeWorkspaceId = "workspace-1";

    const wrapper = mount(ReportsView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.text()).toContain("支付项目");
    expect(wrapper.text()).toContain("50%");
    expect(wrapper.text()).toContain("最新分析评分 88");
    expect(wrapper.text()).toContain("最近 14 日趋势");
    expect(wrapper.text()).toContain("本地确定性初步归因");
    expect(wrapper.text()).toContain("ATTR_PRODUCT_ASSERTION");

    await wrapper.get('[data-testid="export-json-report"]').trigger("click");
    await flushPromises();

    expect(renderReport).toHaveBeenCalledWith("workspace-1", "json");
    expect(saveReportFile).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("C:\\qa\\payment.json");
  });
});
