import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getReport, renderReport, type ReportArtifact, type ReportSnapshot } from "../api/reports";
import { useReportStore } from "./reports";

vi.mock("../api/reports", () => ({ getReport: vi.fn(), renderReport: vi.fn() }));

const snapshot = {
  schema_version: 2,
  workspace_id: "workspace-1",
  workspace_name: "支付项目",
  generated_at: "2026-08-16T12:00:00Z",
  execution_summary: { total: 0, passed: 0, failed: 0, error: 0, cancelled: 0, timeout: 0, active: 0, terminal: 0, evaluated: 0, pass_rate: 0, average_duration_ms: null },
  analysis_summary: { total: 0, passed: 0, failed_or_error: 0, latest_overall_score: null, issue_count: 0 },
  design_summary: { test_point_total: 0, test_point_confirmed: 0, test_case_total: 0, test_case_confirmed: 0 },
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
  failure_attribution_summary: { total: 0, product: 0, environment: 0, data: 0, script: 0, unknown: 0 },
  failure_attributions: [],
  slow_executions: [],
  executions: [],
} satisfies ReportSnapshot;

const artifact = {
  format: "markdown",
  file_name: "payment.md",
  media_type: "text/markdown",
  content: "# private in-flight report\n",
  generated_at: "2026-08-16T12:00:00Z",
} satisfies ReportArtifact;

describe("report store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(getReport).mockReset();
    vi.mocked(renderReport).mockReset();
    Object.defineProperty(window, "desktopBridge", {
      configurable: true,
      value: { saveReportFile: vi.fn() },
    });
  });

  it("loads the active workspace and ignores a stale response after clear", async () => {
    let resolveReport!: (value: ReportSnapshot) => void;
    vi.mocked(getReport).mockReturnValue(new Promise((resolve) => { resolveReport = resolve; }));
    const store = useReportStore();

    const pending = store.refresh("workspace-1");
    store.clear();
    resolveReport(snapshot);
    await pending;

    expect(store.snapshot).toBeNull();
    expect(store.loading).toBe(false);
  });

  it("renders then saves without retaining report content in Pinia", async () => {
    vi.mocked(renderReport).mockResolvedValue(artifact);
    const saveReportFile = vi.mocked(window.desktopBridge!.saveReportFile);
    saveReportFile.mockResolvedValue("C:\\qa\\reports\\payment.md");
    const store = useReportStore();

    await expect(store.exportReport("workspace-1", "markdown")).resolves.toBe(
      "C:\\qa\\reports\\payment.md",
    );

    expect(saveReportFile).toHaveBeenCalledWith(artifact);
    expect(store.lastExportPath).toBe("C:\\qa\\reports\\payment.md");
    expect(JSON.stringify(store.$state)).not.toContain("private in-flight report");
  });

  it("treats dialog cancellation as recoverable and reports a missing desktop bridge", async () => {
    vi.mocked(renderReport).mockResolvedValue(artifact);
    vi.mocked(window.desktopBridge!.saveReportFile).mockResolvedValue(null);
    const store = useReportStore();

    await expect(store.exportReport("workspace-1", "markdown")).resolves.toBeNull();
    expect(store.error).toBeNull();
    expect(store.lastExportPath).toBeNull();

    Object.defineProperty(window, "desktopBridge", { configurable: true, value: undefined });
    await expect(store.exportReport("workspace-1", "markdown")).rejects.toThrow(
      "仅支持在桌面应用中保存报告",
    );
    expect(store.exporting).toBe(false);
    expect(store.error).toContain("仅支持在桌面应用中保存报告");
  });
});
