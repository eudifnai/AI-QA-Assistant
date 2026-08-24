import { defineStore } from "pinia";
import { ref } from "vue";

import {
  getReport,
  renderReport,
  type ReportFormat,
  type ReportSnapshot,
} from "../api/reports";

export const useReportStore = defineStore("reports", () => {
  const snapshot = ref<ReportSnapshot | null>(null);
  const loading = ref(false);
  const exporting = ref(false);
  const error = ref<string | null>(null);
  const lastExportPath = ref<string | null>(null);
  let contextGeneration = 0;

  function messageFrom(reason: unknown): string {
    return reason instanceof Error ? reason.message : "报告操作失败。";
  }

  async function refresh(workspaceId: string): Promise<void> {
    const generation = ++contextGeneration;
    loading.value = true;
    error.value = null;
    try {
      const next = await getReport(workspaceId);
      if (generation !== contextGeneration) return;
      snapshot.value = next;
    } catch (reason: unknown) {
      if (generation !== contextGeneration) return;
      error.value = messageFrom(reason);
    } finally {
      if (generation === contextGeneration) loading.value = false;
    }
  }

  async function exportReport(workspaceId: string, format: ReportFormat): Promise<string | null> {
    const generation = contextGeneration;
    exporting.value = true;
    error.value = null;
    lastExportPath.value = null;
    try {
      const artifact = await renderReport(workspaceId, format);
      if (generation !== contextGeneration) return null;
      const saveReportFile = window.desktopBridge?.saveReportFile;
      if (saveReportFile === undefined) {
        throw new Error("仅支持在桌面应用中保存报告。");
      }
      const result = await saveReportFile(artifact);
      if (generation !== contextGeneration) return null;
      if (result === null) return null;
      if (typeof result !== "string" || result.length === 0) {
        throw new Error("桌面端返回的报告路径不正确。");
      }
      lastExportPath.value = result;
      return result;
    } catch (reason: unknown) {
      if (generation !== contextGeneration) return null;
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) exporting.value = false;
    }
  }

  function clear(): void {
    contextGeneration += 1;
    snapshot.value = null;
    loading.value = false;
    exporting.value = false;
    error.value = null;
    lastExportPath.value = null;
  }

  return { snapshot, loading, exporting, error, lastExportPath, refresh, exportReport, clear };
});
