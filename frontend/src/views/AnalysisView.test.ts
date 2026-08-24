import ElementPlus from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  listDocumentChunks,
  listDocuments,
  type DocumentChunk,
} from "../api/documents";
import { listAnalysisRuns, startAnalysis, type AnalysisRun } from "../api/analysis";
import { getCredentialStatus, getSettings } from "../api/settings";
import {
  batchUpdateTestCases,
  generateTestCases,
  generateTestPoints,
  getTestDesign,
  reviewAnalysisIssue,
  updateTestCase,
  updateTestPoint,
} from "../api/test-design";
import { useWorkspaceStore } from "../stores/workspaces";
import AnalysisView from "./AnalysisView.vue";

vi.mock("../api/analysis", () => ({
  cancelAnalysis: vi.fn(),
  getAnalysisRun: vi.fn(),
  listAnalysisRuns: vi.fn(),
  startAnalysis: vi.fn(),
}));
vi.mock("../api/documents", () => ({ listDocumentChunks: vi.fn(), listDocuments: vi.fn() }));
vi.mock("../api/settings", () => ({
  clearModelCredential: vi.fn(),
  getCredentialStatus: vi.fn(),
  getSettings: vi.fn(),
  saveModelCredential: vi.fn(),
  updateSettings: vi.fn(),
}));
vi.mock("../api/test-design", () => ({
  batchUpdateTestCases: vi.fn(),
  generateTestCases: vi.fn(),
  generateTestPoints: vi.fn(),
  getTestDesign: vi.fn(),
  reviewAnalysisIssue: vi.fn(),
  updateTestCase: vi.fn(),
  updateTestPoint: vi.fn(),
}));
vi.mock("../api/workspaces", () => ({
  createWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
  openWorkspace: vi.fn(),
  renameWorkspace: vi.fn(),
}));

const workspace = {
  id: "workspace-1",
  name: "支付",
  path: "C:\\qa\\pay",
  created_at: "2026-08-12T03:00:00Z",
  last_opened_at: "2026-08-12T03:00:00Z",
};
const document = {
  id: "document-1",
  workspace_id: "workspace-1",
  name: "requirements.md",
  relative_path: "requirements.md",
  created_at: "2026-08-12T03:00:00Z",
  updated_at: "2026-08-12T03:00:00Z",
  latest_version: {
    id: "version-1",
    version_number: 1,
    sha256: "a".repeat(64),
    size_bytes: 120,
    status: "passed" as const,
    parsed_text: "必须支持退款。",
    error_code: null,
    error_message: null,
    created_at: "2026-08-12T03:00:00Z",
  },
  job: {
    id: "job-1",
    status: "passed" as const,
    progress: 100,
    error_code: null,
    error_message: null,
    created_at: "2026-08-12T03:00:00Z",
    started_at: "2026-08-12T03:00:00Z",
    finished_at: "2026-08-12T03:00:01Z",
  },
};
const result: AnalysisRun = {
  id: "run-1",
  workspace_id: "workspace-1",
  document_id: "document-1",
  version_id: "version-1",
  provider: "ollama",
  model_name: "qwen3:8b",
  base_url: "http://127.0.0.1:11434",
  input_chunk_count: 1,
  input_character_count: 7,
  cloud_data_confirmed_at: null,
  status: "passed" as const,
  progress: 100,
  overall_score: 82,
  error_code: null,
  error_message: null,
  created_at: "2026-08-12T03:00:00Z",
  started_at: "2026-08-12T03:00:00Z",
  finished_at: "2026-08-12T03:00:01Z",
  scores: [
    { dimension: "completeness" as const, score: 82, summary: "基本完整" },
    { dimension: "consistency" as const, score: 82, summary: "基本一致" },
    { dimension: "clarity" as const, score: 70, summary: "存在模糊项" },
    { dimension: "testability" as const, score: 75, summary: "部分不可测" },
    { dimension: "feasibility" as const, score: 90, summary: "可行" },
  ],
  issues: [
    {
      id: "issue-1",
      ordinal: 1,
      dimension: "clarity" as const,
      severity: "medium" as const,
      title: "退款期限不清晰",
      description: "没有说明完成期限。",
      impact: "无法设计时间边界测试。",
      suggestion: "补充最长退款时间。",
      question: "退款应在多久内完成？",
      citations: [
        { chunk_id: "chunk-1", ordinal: 1, locator: "第 2 行", text: "必须支持退款。" },
      ],
    },
  ],
};

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const localSettings = {
  theme: "light" as const,
  model_mode: "local" as const,
  model_provider: "ollama" as const,
  model_name: "qwen3:8b",
  base_url: "http://127.0.0.1:11434",
  cloud_data_consent: false,
  updated_at: "2026-08-12T03:00:00Z",
};

const stableChunk: DocumentChunk = {
  id: "chunk-1",
  ordinal: 1,
  source_type: "lines",
  source_start: 1,
  source_end: 1,
  start_offset: 0,
  end_offset: 7,
  text: "必须支持退款。",
  locator: "第 1 行",
};

describe("AnalysisView", () => {
  beforeEach(() => {
    vi.mocked(getTestDesign).mockResolvedValue({
      reviews: [],
      test_points: [],
      test_cases: [],
      traceability: [],
      automation_recommendations: [],
    });
    vi.mocked(reviewAnalysisIssue).mockReset();
    vi.mocked(generateTestPoints).mockReset();
    vi.mocked(generateTestCases).mockReset();
    vi.mocked(batchUpdateTestCases).mockReset();
    vi.mocked(updateTestPoint).mockReset();
    vi.mocked(updateTestCase).mockReset();
  });

  it("discloses the local data scope and renders structured cited findings", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockResolvedValue([stableChunk]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([result]);
    vi.mocked(startAnalysis).mockResolvedValue(result);
    vi.mocked(getSettings).mockResolvedValue(localSettings);

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.text()).toContain("本地 Ollama");
    expect(wrapper.text()).toContain("qwen3:8b");
    expect(wrapper.text()).toContain("仅发送所选文档版本的稳定引用片段");
    expect(wrapper.text()).toContain("完整性");
    expect(wrapper.text()).toContain("退款期限不清晰");
    expect(wrapper.text()).toContain("第 2 行");
    expect(wrapper.text()).toContain("必须支持退款");
    expect(wrapper.text()).toContain("http://127.0.0.1:11434");

    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    await flushPromises();
    expect(startAnalysis).toHaveBeenCalledWith("workspace-1", "document-1", {
      expected_version_id: "version-1",
      expected_provider: "ollama",
      expected_model_name: "qwen3:8b",
      expected_base_url: "http://127.0.0.1:11434",
      expected_input_chunk_count: 1,
      expected_input_character_count: 7,
      cloud_data_confirmed: false,
    });
  });

  it("waits for a non-empty local chunk scope before enabling analysis", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    const chunksRequest = deferred<DocumentChunk[]>();
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockReturnValue(chunksRequest.promise);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    vi.mocked(startAnalysis).mockResolvedValue(result);

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.get('[data-testid="start-analysis"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    expect(startAnalysis).not.toHaveBeenCalled();

    chunksRequest.resolve([stableChunk]);
    await flushPromises();

    expect(wrapper.get('[data-testid="start-analysis"]').attributes("disabled")).toBeUndefined();
    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    await flushPromises();
    expect(startAnalysis).toHaveBeenCalledTimes(1);
  });

  it("keeps local analysis disabled and explains a chunk loading failure", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockRejectedValue(new Error("稳定片段读取失败"));
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
    vi.mocked(getSettings).mockResolvedValue(localSettings);

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.text()).toContain("无法确认分析范围：稳定片段读取失败");
    expect(wrapper.get('[data-testid="start-analysis"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("requires a fresh cloud confirmation and sends the exact snapshot once", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    const chunks = [
      {
        id: "chunk-1",
        ordinal: 1,
        source_type: "lines" as const,
        source_start: 1,
        source_end: 2,
        start_offset: 0,
        end_offset: 12,
        text: "必须支持退款。",
        locator: "第 1-2 行",
      },
      {
        id: "chunk-2",
        ordinal: 2,
        source_type: "lines" as const,
        source_start: 3,
        source_end: 3,
        start_offset: 12,
        end_offset: 18,
        text: "退款可撤销。",
        locator: "第 3 行",
      },
    ];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockResolvedValue(chunks);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
    vi.mocked(getCredentialStatus).mockResolvedValue({ configured: true });
    vi.mocked(getSettings).mockResolvedValue({
      theme: "light",
      model_mode: "cloud",
      model_provider: "openai_compatible",
      model_name: "qa-cloud",
      base_url: "https://models.example.com/v1",
      cloud_data_consent: true,
      updated_at: "2026-08-12T03:00:00Z",
    });
    vi.mocked(startAnalysis).mockResolvedValue({
      ...result,
      provider: "openai_compatible",
      model_name: "qa-cloud",
      base_url: "https://models.example.com/v1",
      input_chunk_count: 2,
      input_character_count: 13,
      cloud_data_confirmed_at: "2026-08-12T03:00:00Z",
    });

    const wrapper = mount(AnalysisView, {
      attachTo: globalThis.document.body,
      global: { plugins: [pinia, ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    await flushPromises();
    expect(startAnalysis).not.toHaveBeenCalled();
    expect(globalThis.document.body.textContent).toContain("即将发送到云端模型");
    expect(globalThis.document.body.textContent).toContain(
      "https://models.example.com/v1/chat/completions",
    );
    expect(globalThis.document.body.textContent).toContain("requirements.md · v1");
    expect(globalThis.document.body.textContent).toContain("全部 2 个片段，共 13 个字符");

    const cancelButton = globalThis.document.body.querySelector<HTMLElement>(
      '[data-testid="cancel-cloud-analysis"]',
    );
    expect(cancelButton).not.toBeNull();
    cancelButton?.click();
    await flushPromises();
    expect(startAnalysis).not.toHaveBeenCalled();

    await wrapper.get('[data-testid="start-analysis"]').trigger("click");
    await flushPromises();
    const acknowledgement = globalThis.document.body.querySelector<HTMLInputElement>(
      '[data-testid="cloud-run-consent"] input',
    );
    expect(acknowledgement).not.toBeNull();
    acknowledgement?.click();
    await flushPromises();
    const confirmButton = globalThis.document.body.querySelector<HTMLElement>(
      '[data-testid="confirm-cloud-analysis"]',
    );
    confirmButton?.click();
    confirmButton?.click();
    await flushPromises();

    expect(startAnalysis).toHaveBeenCalledTimes(1);
    expect(startAnalysis).toHaveBeenCalledWith("workspace-1", "document-1", {
      expected_version_id: "version-1",
      expected_provider: "openai_compatible",
      expected_model_name: "qa-cloud",
      expected_base_url: "https://models.example.com/v1",
      expected_input_chunk_count: 2,
      expected_input_character_count: 13,
      cloud_data_confirmed: true,
    });
    expect(wrapper.text()).toContain("https://models.example.com/v1/chat/completions");
    wrapper.unmount();
  });

  it("keeps cloud analysis disabled when credential status fails and supports retry", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
    vi.mocked(getSettings).mockResolvedValue({
      theme: "light",
      model_mode: "cloud",
      model_provider: "openai_compatible",
      model_name: "qa-cloud",
      base_url: "https://models.example.com/v1",
      cloud_data_consent: true,
      updated_at: "2026-08-12T03:00:00Z",
    });
    vi.mocked(getCredentialStatus)
      .mockRejectedValueOnce(new Error("无法读取系统凭据库。"))
      .mockResolvedValueOnce({ configured: true });

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.text()).toContain("无法读取系统凭据库");
    expect(wrapper.get('[data-testid="start-analysis"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="retry-credential-status"]').trigger("click");
    await flushPromises();

    expect(getCredentialStatus).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).not.toContain("无法读取系统凭据库");
  });

  it("reviews an issue, generates one traceable draft, and edits it", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockResolvedValue([stableChunk]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([result]);
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    const review = {
      id: "review-1",
      run_id: "run-1",
      issue_id: "issue-1",
      status: "accepted" as const,
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
      test_type: "boundary" as const,
      priority: "P1" as const,
      status: "draft" as const,
      automation_candidate: false,
      created_at: "2026-08-14T03:00:00Z",
      updated_at: "2026-08-14T03:00:00Z",
    };
    const testCase = {
      id: "case-1",
      run_id: "run-1",
      source_test_point_id: "point-1",
      title: "验证退款期限边界",
      preconditions: ["退款服务可用"],
      priority: "P1" as const,
      tags: ["boundary"],
      automation_type: "manual" as const,
      status: "draft" as const,
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
    vi.mocked(getTestDesign).mockResolvedValue({
      reviews: [],
      test_points: [],
      test_cases: [],
      traceability: [],
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
    vi.mocked(reviewAnalysisIssue).mockResolvedValue(review);
    vi.mocked(generateTestPoints).mockResolvedValue([point]);
    vi.mocked(updateTestPoint)
      .mockResolvedValueOnce({ ...point, automation_candidate: true })
      .mockResolvedValue({ ...point, status: "confirmed", automation_candidate: true });
    vi.mocked(generateTestCases).mockResolvedValue([testCase]);
    vi.mocked(updateTestCase).mockResolvedValue({ ...testCase, automation_type: "api" });
    vi.mocked(batchUpdateTestCases).mockResolvedValue([
      { ...testCase, automation_type: "api", status: "confirmed" },
    ]);

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    await wrapper.get('[data-testid="review-accepted-issue-1"] input').setValue(true);
    await wrapper.get('[data-testid="review-answer-issue-1"]').setValue("24 小时内完成");
    await wrapper.get('[data-testid="save-review-issue-1"]').trigger("click");
    await flushPromises();
    expect(reviewAnalysisIssue).toHaveBeenCalledWith("workspace-1", "run-1", "issue-1", {
      status: "accepted",
      answer: "24 小时内完成",
    });

    await wrapper.get('[data-testid="generate-test-points"]').trigger("click");
    await flushPromises();
    expect(generateTestPoints).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("来源：退款期限不清晰");
    expect(wrapper.text()).toContain("建议优先采用 API 自动化");

    await wrapper.get('[data-testid="apply-point-automation-point-1"]').trigger("click");
    await flushPromises();
    expect(updateTestPoint).toHaveBeenLastCalledWith(
      "workspace-1",
      "run-1",
      "point-1",
      expect.objectContaining({ automation_candidate: true }),
    );

    await wrapper.get('[data-testid="point-title-point-1"]').setValue("验证退款期限边界");
    await wrapper.get('[data-testid="save-test-point-point-1"]').trigger("click");
    await flushPromises();
    expect(updateTestPoint).toHaveBeenLastCalledWith(
      "workspace-1",
      "run-1",
      "point-1",
      expect.objectContaining({ title: "验证退款期限边界" }),
    );

    await wrapper.get('[data-testid="generate-test-cases"]').trigger("click");
    await flushPromises();
    expect(generateTestCases).toHaveBeenCalledTimes(1);
    expect(
      wrapper.get('[data-testid="case-step-action-case-1-0"]').element,
    ).toHaveProperty("value", "提交退款申请");
    expect(
      wrapper.get('[data-testid="case-step-expected-case-1-0"]').element,
    ).toHaveProperty("value", "退款在 24 小时内完成");

    await wrapper.get('[data-testid="apply-case-automation-case-1"]').trigger("click");
    await flushPromises();
    expect(updateTestCase).toHaveBeenLastCalledWith(
      "workspace-1",
      "run-1",
      "case-1",
      expect.objectContaining({ automation_type: "api" }),
    );

    await wrapper.get('[data-testid="case-title-case-1"]').setValue("退款 API 边界用例");
    await wrapper.get('[data-testid="save-test-case-case-1"]').trigger("click");
    await flushPromises();
    expect(updateTestCase).toHaveBeenLastCalledWith(
      "workspace-1",
      "run-1",
      "case-1",
      expect.objectContaining({ title: "退款 API 边界用例" }),
    );

    await wrapper.get('[data-testid="select-test-case-case-1"] input').setValue(true);
    await wrapper.get('[data-testid="batch-confirm-test-cases"]').trigger("click");
    await flushPromises();
    expect(batchUpdateTestCases).toHaveBeenCalledWith("workspace-1", "run-1", {
      test_case_ids: ["case-1"],
      status: "confirmed",
    });
  });

  it("renders and filters the derived requirement traceability matrix", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(listDocumentChunks).mockResolvedValue([stableChunk]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([result]);
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    vi.mocked(getTestDesign).mockResolvedValue({
      reviews: [],
      test_points: [],
      test_cases: [],
      traceability: [
        {
          issue_id: "issue-1",
          issue_title: "退款期限不清晰",
          dimension: "clarity",
          severity: "high",
          citations: [
            {
              chunk_id: "chunk-1",
              ordinal: 1,
              locator: "第 2 行",
              text: "必须支持退款。",
            },
          ],
          review_status: "accepted",
          review_answer: "24 小时内完成",
          test_point_id: "point-1",
          test_point_title: "验证退款期限",
          test_point_status: "confirmed",
          test_case_id: "case-1",
          test_case_title: "退款期限边界",
          test_case_status: "confirmed",
          coverage_status: "covered",
        },
        {
          issue_id: "issue-2",
          issue_title: "退款权限未说明",
          dimension: "completeness",
          severity: "medium",
          citations: [],
          review_status: null,
          review_answer: null,
          test_point_id: null,
          test_point_title: null,
          test_point_status: null,
          test_case_id: null,
          test_case_title: null,
          test_case_status: null,
          coverage_status: "unreviewed",
        },
      ],
      automation_recommendations: [],
    });

    const wrapper = mount(AnalysisView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    expect(wrapper.text()).toContain("需求追踪矩阵");
    expect(wrapper.text()).toContain("已覆盖 1");
    expect(wrapper.text()).toContain("待处理 1");
    expect(wrapper.findAll('[data-testid^="traceability-row-"]')).toHaveLength(2);
    expect(wrapper.text()).toContain("第 2 行 · chunk-1");

    await wrapper.get('[data-testid="traceability-filter"]').setValue("covered");
    expect(wrapper.findAll('[data-testid^="traceability-row-"]')).toHaveLength(1);
    expect(wrapper.text()).toContain("退款期限不清晰");
    expect(wrapper.text()).not.toContain("退款权限未说明");
  });
});
