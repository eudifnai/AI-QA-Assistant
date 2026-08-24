import ElementPlus from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import {
  resolveDroppedDocumentPaths,
  selectDocumentFiles,
} from "../api/backend-connection";
import { importDocuments, listDocumentChunks, listDocuments } from "../api/documents";
import { useWorkspaceStore } from "../stores/workspaces";
import DocumentsView from "./DocumentsView.vue";

vi.mock("../api/backend-connection", () => ({
  resolveDroppedDocumentPaths: vi.fn(),
  selectDocumentFiles: vi.fn(),
}));
vi.mock("../api/documents", () => ({
  cancelDocumentJob: vi.fn(),
  importDocuments: vi.fn(),
  listDocuments: vi.fn(),
  listDocumentChunks: vi.fn(),
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
  created_at: "2026-08-10T03:00:00Z",
  last_opened_at: "2026-08-10T03:00:00Z",
};
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
    status: "passed" as const,
    parsed_text: "# 支付需求\n必须支持退款。",
    error_code: null,
    error_message: null,
    created_at: "2026-08-10T03:00:00Z",
  },
  job: {
    id: "job-1",
    status: "passed" as const,
    progress: 100,
    error_code: null,
    error_message: null,
    created_at: "2026-08-10T03:00:00Z",
    started_at: "2026-08-10T03:00:01Z",
    finished_at: "2026-08-10T03:00:02Z",
  },
};

describe("DocumentsView", () => {
  it("selects a local file and displays parsed preview", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([document]);
    vi.mocked(selectDocumentFiles).mockResolvedValue([
      "C:\\qa\\pay\\requirements.md",
      "C:\\qa\\pay\\unsupported.rtf",
    ]);
    vi.mocked(importDocuments).mockResolvedValue([
      {
        source_path: "C:\\qa\\pay\\requirements.md",
        status: "accepted",
        document,
        error_code: null,
        error_message: null,
      },
      {
        source_path: "C:\\qa\\pay\\unsupported.rtf",
        status: "rejected",
        document: null,
        error_code: "DOCUMENT_FORMAT_UNSUPPORTED",
        error_message: "当前仅支持 Markdown、TXT、DOCX 和 PDF 文件。",
      },
    ]);
    vi.mocked(listDocumentChunks).mockResolvedValue([
      {
        id: "chunk-1",
        ordinal: 1,
        source_type: "lines",
        source_start: 1,
        source_end: 2,
        start_offset: 0,
        end_offset: 15,
        text: "# 支付需求\n必须支持退款。",
        locator: "第 1-2 行",
      },
    ]);

    const wrapper = mount(DocumentsView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();
    await wrapper.get('[data-testid="select-document-file"]').trigger("click");
    await flushPromises();

    expect(importDocuments).toHaveBeenCalledWith(
      "workspace-1",
      ["C:\\qa\\pay\\requirements.md", "C:\\qa\\pay\\unsupported.rtf"],
    );
    expect(wrapper.text()).toContain("支持多选或拖入 Markdown、TXT、DOCX 和 PDF");
    expect(wrapper.text()).toContain("必须支持退款");
    expect(wrapper.text()).toContain("第 1-2 行");
    expect(wrapper.find('[data-chunk-id="chunk-1"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("1 个文件已加入解析，1 个文件未导入");
  });

  it("imports files dropped from the operating system", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const workspaces = useWorkspaceStore();
    workspaces.items = [workspace];
    vi.mocked(listDocuments).mockResolvedValue([]);
    vi.mocked(resolveDroppedDocumentPaths).mockResolvedValue([
      "C:\\qa\\pay\\requirements.md",
    ]);
    vi.mocked(listDocumentChunks).mockResolvedValue([]);
    vi.mocked(importDocuments).mockResolvedValue([
      {
        source_path: "C:\\qa\\pay\\requirements.md",
        status: "accepted",
        document,
        error_code: null,
        error_message: null,
      },
    ]);
    const wrapper = mount(DocumentsView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();
    const file = {} as File;

    await wrapper.get('[data-testid="document-drop-zone"]').trigger("drop", {
      dataTransfer: { files: [file] },
    });
    await flushPromises();

    expect(resolveDroppedDocumentPaths).toHaveBeenCalledWith([file]);
    expect(importDocuments).toHaveBeenCalledWith("workspace-1", [
      "C:\\qa\\pay\\requirements.md",
    ]);
  });
});
