import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelDocumentJob,
  importDocument,
  importDocuments,
  listDocumentChunks,
  listDocuments,
  type DocumentChunk,
} from "../api/documents";
import { useDocumentStore } from "./documents";

vi.mock("../api/documents", () => ({
  cancelDocumentJob: vi.fn(),
  importDocument: vi.fn(),
  importDocuments: vi.fn(),
  listDocuments: vi.fn(),
  listDocumentChunks: vi.fn(),
}));

const document = {
  id: "document-1",
  workspace_id: "workspace-1",
  name: "requirements.md",
  relative_path: "requirements.md",
  created_at: "2026-08-10T03:00:00Z",
  updated_at: "2026-08-10T03:00:00Z",
  latest_version: {
    id: "version-1",
    version_number: 1,
    sha256: "a".repeat(64),
    size_bytes: 120,
    status: "queued" as const,
    parsed_text: null,
    error_code: null,
    error_message: null,
    created_at: "2026-08-10T03:00:00Z",
  },
  job: {
    id: "job-1",
    status: "queued" as const,
    progress: 0,
    error_code: null,
    error_message: null,
    created_at: "2026-08-10T03:00:00Z",
    started_at: null,
    finished_at: null,
  },
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

const firstChunk: DocumentChunk = {
  id: "chunk-1",
  ordinal: 1,
  source_type: "lines",
  source_start: 1,
  source_end: 2,
  start_offset: 0,
  end_offset: 12,
  text: "# 需求\n必须退款",
  locator: "第 1-2 行",
};

describe("document store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(listDocuments).mockReset();
    vi.mocked(importDocument).mockReset();
    vi.mocked(importDocuments).mockReset();
    vi.mocked(listDocumentChunks).mockReset();
    vi.mocked(cancelDocumentJob).mockReset();
  });

  it("loads and imports documents", async () => {
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(importDocument).mockResolvedValue(document);
    const store = useDocumentStore();

    await store.refresh("workspace-1");
    await store.importFile("workspace-1", "C:\\qa\\requirements.md");

    expect(store.items).toEqual([document]);
    expect(store.selected?.id).toBe("document-1");
  });

  it("cancels a running job", async () => {
    vi.mocked(cancelDocumentJob).mockResolvedValue({
      ...document,
      job: { ...document.job, status: "cancelled" },
    });
    const store = useDocumentStore();
    store.items = [document];

    await store.cancel("job-1");

    expect(store.items[0]?.job.status).toBe("cancelled");
  });

  it("loads stable chunks for the selected document", async () => {
    vi.mocked(listDocumentChunks).mockResolvedValue([firstChunk]);
    const store = useDocumentStore();

    await store.loadChunks("workspace-1", "document-1");

    expect(store.chunks[0]?.locator).toBe("第 1-2 行");
  });

  it("ignores an older successful chunk response after the document changes", async () => {
    const oldRequest = deferred<DocumentChunk[]>();
    const newChunk = { ...firstChunk, id: "chunk-2", text: "新的文档", locator: "第 3 行" };
    vi.mocked(listDocumentChunks)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce([newChunk]);
    const store = useDocumentStore();

    const oldLoad = store.loadChunks("workspace-1", "document-1");
    await store.loadChunks("workspace-1", "document-2");
    oldRequest.resolve([firstChunk]);
    await oldLoad;

    expect(store.chunks).toEqual([newChunk]);
    expect(store.loadingChunks).toBe(false);
    expect(store.error).toBeNull();
  });

  it("ignores an older failed chunk response after a newer load succeeds", async () => {
    const oldRequest = deferred<DocumentChunk[]>();
    const newChunk = { ...firstChunk, id: "chunk-2", text: "新的文档" };
    vi.mocked(listDocumentChunks)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce([newChunk]);
    const store = useDocumentStore();

    const oldLoad = store.loadChunks("workspace-1", "document-1");
    await store.loadChunks("workspace-1", "document-2");
    oldRequest.reject(new Error("旧文档读取失败"));
    await oldLoad;

    expect(store.chunks).toEqual([newChunk]);
    expect(store.error).toBeNull();
  });

  it("invalidates an in-flight chunk response when chunks are cleared", async () => {
    const request = deferred<DocumentChunk[]>();
    vi.mocked(listDocumentChunks).mockReturnValue(request.promise);
    const store = useDocumentStore();

    const load = store.loadChunks("workspace-1", "document-1");
    store.clearChunks();
    request.resolve([firstChunk]);
    await load;

    expect(store.chunks).toEqual([]);
    expect(store.loadingChunks).toBe(false);
  });

  it("merges accepted batch items and retains rejected results", async () => {
    vi.mocked(importDocuments).mockResolvedValue([
      {
        source_path: "C:\\qa\\requirements.md",
        status: "accepted",
        document,
        error_code: null,
        error_message: null,
      },
      {
        source_path: "C:\\qa\\unsupported.rtf",
        status: "rejected",
        document: null,
        error_code: "DOCUMENT_FORMAT_UNSUPPORTED",
        error_message: "当前仅支持 Markdown、TXT、DOCX 和 PDF 文件。",
      },
    ]);
    const store = useDocumentStore();

    await store.importFiles("workspace-1", [
      "C:\\qa\\requirements.md",
      "C:\\qa\\unsupported.rtf",
    ]);

    expect(store.items).toEqual([document]);
    expect(store.importResults).toHaveLength(2);
    expect(store.error).toBeNull();
  });
});
