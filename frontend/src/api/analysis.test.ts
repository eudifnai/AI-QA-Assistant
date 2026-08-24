import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { listAnalysisRuns, startAnalysis } from "./analysis";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

const run = {
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
  status: "passed",
  progress: 100,
  overall_score: 82,
  error_code: null,
  error_message: null,
  created_at: "2026-08-12T03:00:00Z",
  started_at: "2026-08-12T03:00:01Z",
  finished_at: "2026-08-12T03:00:02Z",
  scores: [
    { dimension: "completeness", score: 82, summary: "基本完整" },
    { dimension: "consistency", score: 82, summary: "基本一致" },
    { dimension: "clarity", score: 82, summary: "基本清晰" },
    { dimension: "testability", score: 82, summary: "基本可测" },
    { dimension: "feasibility", score: 82, summary: "基本可行" },
  ],
  issues: [
    {
      id: "issue-1",
      ordinal: 1,
      dimension: "clarity",
      severity: "medium",
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

describe("analysis API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("starts a document analysis and validates its stable citations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(run), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const input = {
      expected_version_id: "version-1",
      expected_provider: "ollama" as const,
      expected_model_name: "qwen3:8b",
      expected_base_url: "http://127.0.0.1:11434",
      expected_input_chunk_count: 1,
      expected_input_character_count: 7,
      cloud_data_confirmed: false,
    };

    await expect(startAnalysis("workspace-1", "document-1", input)).resolves.toEqual(run);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/documents/document-1/analysis-runs",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("rejects malformed results without all five dimensions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([{ ...run, scores: run.scores.slice(0, 4) }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listAnalysisRuns("workspace-1", "document-1")).rejects.toEqual(
      expect.objectContaining({ code: "INVALID_RESPONSE" }),
    );
  });
});
