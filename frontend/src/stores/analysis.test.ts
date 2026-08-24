import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelAnalysis,
  getAnalysisRun,
  listAnalysisRuns,
  startAnalysis,
  type AnalysisRun,
} from "../api/analysis";
import { useAnalysisStore } from "./analysis";

vi.mock("../api/analysis", () => ({
  cancelAnalysis: vi.fn(),
  getAnalysisRun: vi.fn(),
  listAnalysisRuns: vi.fn(),
  startAnalysis: vi.fn(),
}));

const queued: AnalysisRun = {
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
  status: "queued",
  progress: 0,
  overall_score: null,
  error_code: null,
  error_message: null,
  created_at: "2026-08-12T03:00:00Z",
  started_at: null,
  finished_at: null,
  scores: [],
  issues: [],
};

const startInput = {
  expected_version_id: "version-1",
  expected_provider: "ollama" as const,
  expected_model_name: "qwen3:8b",
  expected_base_url: "http://127.0.0.1:11434",
  expected_input_chunk_count: 1,
  expected_input_character_count: 7,
  cloud_data_confirmed: false,
};

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("analysis store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(cancelAnalysis).mockReset();
    vi.mocked(getAnalysisRun).mockReset();
    vi.mocked(listAnalysisRuns).mockReset();
    vi.mocked(startAnalysis).mockReset();
  });

  it("starts and refreshes a selected run", async () => {
    vi.mocked(startAnalysis).mockResolvedValue(queued);
    vi.mocked(getAnalysisRun).mockResolvedValue({ ...queued, status: "running", progress: 60 });
    const store = useAnalysisStore();

    await store.start("workspace-1", "document-1", startInput);
    await expect(store.refreshSelected("workspace-1")).resolves.toBe(true);

    expect(startAnalysis).toHaveBeenCalledWith("workspace-1", "document-1", startInput);
    expect(store.selected?.status).toBe("running");
    expect(store.items[0]?.progress).toBe(60);
  });

  it("ignores a stale poll response after the selected run changes", async () => {
    let resolvePoll: ((run: AnalysisRun) => void) | undefined;
    vi.mocked(getAnalysisRun).mockReturnValue(
      new Promise<AnalysisRun>((resolve) => {
        resolvePoll = resolve;
      }),
    );
    const store = useAnalysisStore();
    const other = { ...queued, id: "run-2", model_name: "other-model" };
    store.items = [queued, other];
    store.selected = queued;

    const pending = store.refreshSelected("workspace-1");
    store.selected = other;
    resolvePoll?.({ ...queued, status: "running", progress: 80 });
    await pending;

    expect(store.selected?.id).toBe("run-2");
    expect(store.items.find((item) => item.id === "run-1")?.progress).toBe(0);
  });

  it("reports a polling failure so the caller can pause automatic retries", async () => {
    vi.mocked(getAnalysisRun).mockRejectedValue(new Error("模型服务暂时不可用"));
    const store = useAnalysisStore();
    store.items = [queued];
    store.selected = queued;

    await expect(store.refreshSelected("workspace-1")).resolves.toBe(false);

    expect(store.error).toBe("模型服务暂时不可用");
  });

  it("ignores an older successful list response after the analysis context changes", async () => {
    const oldRequest = deferred<AnalysisRun[]>();
    const newer = { ...queued, id: "run-2", document_id: "document-2" };
    vi.mocked(listAnalysisRuns)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce([newer]);
    const store = useAnalysisStore();

    const oldRefresh = store.refresh("workspace-1", "document-1");
    await store.refresh("workspace-1", "document-2");
    oldRequest.resolve([queued]);
    await oldRefresh;

    expect(store.items).toEqual([newer]);
    expect(store.selected?.id).toBe("run-2");
    expect(store.loading).toBe(false);
  });

  it("ignores an older failed list response after a newer refresh succeeds", async () => {
    const oldRequest = deferred<AnalysisRun[]>();
    const newer = { ...queued, id: "run-2", document_id: "document-2" };
    vi.mocked(listAnalysisRuns)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce([newer]);
    const store = useAnalysisStore();

    const oldRefresh = store.refresh("workspace-1", "document-1");
    await store.refresh("workspace-1", "document-2");
    oldRequest.reject(new Error("旧记录读取失败"));
    await oldRefresh;

    expect(store.items).toEqual([newer]);
    expect(store.error).toBeNull();
  });

  it("invalidates an in-flight list response when the analysis context is cleared", async () => {
    const request = deferred<AnalysisRun[]>();
    vi.mocked(listAnalysisRuns).mockReturnValue(request.promise);
    const store = useAnalysisStore();

    const refresh = store.refresh("workspace-1", "document-1");
    store.clear();
    request.resolve([queued]);
    await refresh;

    expect(store.items).toEqual([]);
    expect(store.selected).toBeNull();
    expect(store.loading).toBe(false);
  });

  it("cancels the active worker run", async () => {
    vi.mocked(cancelAnalysis).mockResolvedValue({ ...queued, status: "cancelled", progress: 100 });
    const store = useAnalysisStore();
    store.items = [queued];
    store.selected = queued;

    await store.cancel("workspace-1");

    expect(store.selected?.status).toBe("cancelled");
  });

  it("invalidates an in-flight successful start when the context is cleared", async () => {
    const request = deferred<AnalysisRun>();
    vi.mocked(startAnalysis).mockReturnValue(request.promise);
    const store = useAnalysisStore();

    const start = store.start("workspace-1", "document-1", startInput);
    expect(store.starting).toBe(true);
    store.clear();
    request.resolve(queued);
    await start;

    expect(store.items).toEqual([]);
    expect(store.selected).toBeNull();
    expect(store.starting).toBe(false);
    expect(store.error).toBeNull();
  });

  it("ignores an in-flight start failure from a cleared context", async () => {
    const request = deferred<AnalysisRun>();
    vi.mocked(startAnalysis).mockReturnValue(request.promise);
    const store = useAnalysisStore();

    const start = store.start("workspace-1", "document-1", startInput);
    store.clear();
    request.reject(new Error("旧启动失败"));
    await expect(start).resolves.toBeUndefined();

    expect(store.error).toBeNull();
    expect(store.starting).toBe(false);
  });

  it("invalidates successful and failed cancel responses after the context is cleared", async () => {
    const successRequest = deferred<AnalysisRun>();
    vi.mocked(cancelAnalysis).mockReturnValueOnce(successRequest.promise);
    const store = useAnalysisStore();
    store.items = [queued];
    store.selected = queued;

    const successfulCancel = store.cancel("workspace-1");
    expect(store.cancelling).toBe(true);
    store.clear();
    successRequest.resolve({ ...queued, status: "cancelled", progress: 100 });
    await successfulCancel;

    expect(store.items).toEqual([]);
    expect(store.selected).toBeNull();
    expect(store.cancelling).toBe(false);

    const failureRequest = deferred<AnalysisRun>();
    vi.mocked(cancelAnalysis).mockReturnValueOnce(failureRequest.promise);
    store.items = [queued];
    store.selected = queued;
    const failedCancel = store.cancel("workspace-1");
    store.clear();
    failureRequest.reject(new Error("旧取消失败"));
    await expect(failedCancel).resolves.toBeUndefined();

    expect(store.error).toBeNull();
    expect(store.cancelling).toBe(false);
  });

  it("keeps current-context start and cancel failures recoverable", async () => {
    vi.mocked(startAnalysis).mockRejectedValueOnce(new Error("当前启动失败"));
    const store = useAnalysisStore();

    await expect(store.start("workspace-1", "document-1", startInput)).rejects.toThrow(
      "当前启动失败",
    );
    expect(store.error).toBe("当前启动失败");
    expect(store.starting).toBe(false);

    store.items = [queued];
    store.selected = queued;
    vi.mocked(cancelAnalysis).mockRejectedValueOnce(new Error("当前取消失败"));
    await expect(store.cancel("workspace-1")).rejects.toThrow("当前取消失败");
    expect(store.error).toBe("当前取消失败");
    expect(store.cancelling).toBe(false);
  });
});
