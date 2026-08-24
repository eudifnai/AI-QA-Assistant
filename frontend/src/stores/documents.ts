import { defineStore } from "pinia";
import { ref } from "vue";

import {
  cancelDocumentJob,
  importDocument,
  importDocuments,
  listDocumentChunks,
  listDocuments,
  type DocumentChunk,
  type DocumentImportResult,
  type DocumentItem,
} from "../api/documents";

export const useDocumentStore = defineStore("documents", () => {
  const items = ref<DocumentItem[]>([]);
  const selected = ref<DocumentItem | null>(null);
  const chunks = ref<DocumentChunk[]>([]);
  const importResults = ref<DocumentImportResult[]>([]);
  const loading = ref(false);
  const importing = ref(false);
  const cancellingJobId = ref<string | null>(null);
  const loadingChunks = ref(false);
  const error = ref<string | null>(null);
  let chunkRequestGeneration = 0;

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "文档操作失败。";
  }

  async function refresh(workspaceId: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await listDocuments(workspaceId);
      selected.value =
        items.value.find((item) => item.id === selected.value?.id) ?? items.value[0] ?? null;
    } catch (reason: unknown) {
      error.value = message(reason);
    } finally {
      loading.value = false;
    }
  }

  async function importFile(workspaceId: string, sourcePath: string): Promise<void> {
    importing.value = true;
    error.value = null;
    importResults.value = [];
    try {
      const created = await importDocument(workspaceId, sourcePath);
      items.value = [created, ...items.value.filter((item) => item.id !== created.id)];
      selected.value = created;
      chunks.value = [];
    } catch (reason: unknown) {
      error.value = message(reason);
      throw reason;
    } finally {
      importing.value = false;
    }
  }

  async function importFiles(
    workspaceId: string,
    sourcePaths: string[],
  ): Promise<DocumentImportResult[]> {
    importing.value = true;
    error.value = null;
    importResults.value = [];
    try {
      const results = await importDocuments(workspaceId, sourcePaths);
      importResults.value = results;
      const accepted = results.flatMap((result) =>
        result.status === "accepted" && result.document !== null ? [result.document] : [],
      );
      const acceptedIds = new Set(accepted.map((document) => document.id));
      items.value = [...accepted, ...items.value.filter((item) => !acceptedIds.has(item.id))];
      if (accepted[0] !== undefined) {
        selected.value = accepted[0];
        chunks.value = [];
      }
      return results;
    } catch (reason: unknown) {
      error.value = message(reason);
      throw reason;
    } finally {
      importing.value = false;
    }
  }

  async function cancel(jobId: string): Promise<void> {
    cancellingJobId.value = jobId;
    error.value = null;
    try {
      const updated = await cancelDocumentJob(jobId);
      items.value = items.value.map((item) => (item.id === updated.id ? updated : item));
      if (selected.value?.id === updated.id) selected.value = updated;
    } catch (reason: unknown) {
      error.value = message(reason);
      throw reason;
    } finally {
      cancellingJobId.value = null;
    }
  }

  async function loadChunks(workspaceId: string, documentId: string): Promise<void> {
    const requestGeneration = ++chunkRequestGeneration;
    loadingChunks.value = true;
    error.value = null;
    try {
      const loadedChunks = await listDocumentChunks(workspaceId, documentId);
      if (requestGeneration !== chunkRequestGeneration) return;
      chunks.value = loadedChunks;
    } catch (reason: unknown) {
      if (requestGeneration !== chunkRequestGeneration) return;
      chunks.value = [];
      error.value = message(reason);
    } finally {
      if (requestGeneration === chunkRequestGeneration) loadingChunks.value = false;
    }
  }

  function clearChunks(): void {
    chunkRequestGeneration += 1;
    chunks.value = [];
    loadingChunks.value = false;
  }

  function clearImportResults(): void {
    importResults.value = [];
  }

  return {
    items,
    selected,
    chunks,
    importResults,
    loading,
    importing,
    cancellingJobId,
    loadingChunks,
    error,
    refresh,
    importFile,
    importFiles,
    cancel,
    loadChunks,
    clearChunks,
    clearImportResults,
  };
});
