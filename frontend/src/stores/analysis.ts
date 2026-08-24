import { defineStore } from "pinia";
import { ref } from "vue";

import {
  cancelAnalysis,
  getAnalysisRun,
  listAnalysisRuns,
  startAnalysis,
  type AnalysisRun,
  type AnalysisStartInput,
} from "../api/analysis";

export const useAnalysisStore = defineStore("analysis", () => {
  const items = ref<AnalysisRun[]>([]);
  const selected = ref<AnalysisRun | null>(null);
  const loading = ref(false);
  const starting = ref(false);
  const cancelling = ref(false);
  const error = ref<string | null>(null);
  let refreshGeneration = 0;
  let contextGeneration = 0;

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "需求分析操作失败。";
  }

  function replace(run: AnalysisRun): void {
    items.value = [run, ...items.value.filter((item) => item.id !== run.id)];
    selected.value = run;
  }

  async function refresh(workspaceId: string, documentId: string): Promise<void> {
    const requestGeneration = ++refreshGeneration;
    loading.value = true;
    error.value = null;
    try {
      const refreshedItems = await listAnalysisRuns(workspaceId, documentId);
      if (requestGeneration !== refreshGeneration) return;
      items.value = refreshedItems;
      selected.value =
        items.value.find((item) => item.id === selected.value?.id) ?? items.value[0] ?? null;
    } catch (reason: unknown) {
      if (requestGeneration !== refreshGeneration) return;
      error.value = message(reason);
    } finally {
      if (requestGeneration === refreshGeneration) loading.value = false;
    }
  }

  async function start(
    workspaceId: string,
    documentId: string,
    input: AnalysisStartInput,
  ): Promise<void> {
    const requestContext = contextGeneration;
    starting.value = true;
    error.value = null;
    try {
      const startedRun = await startAnalysis(workspaceId, documentId, input);
      if (requestContext !== contextGeneration) return;
      replace(startedRun);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) starting.value = false;
    }
  }

  async function refreshSelected(workspaceId: string): Promise<boolean> {
    if (selected.value === null) return true;
    const requestedRunId = selected.value.id;
    try {
      const refreshed = await getAnalysisRun(workspaceId, requestedRunId);
      if (selected.value?.id !== requestedRunId) return true;
      replace(refreshed);
      error.value = null;
      return true;
    } catch (reason: unknown) {
      if (selected.value?.id !== requestedRunId) return true;
      error.value = message(reason);
      return false;
    }
  }

  async function cancel(workspaceId: string): Promise<void> {
    if (selected.value === null) return;
    const requestContext = contextGeneration;
    const requestedRunId = selected.value.id;
    cancelling.value = true;
    error.value = null;
    try {
      const cancelledRun = await cancelAnalysis(workspaceId, requestedRunId);
      if (requestContext !== contextGeneration || selected.value?.id !== requestedRunId) return;
      replace(cancelledRun);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration || selected.value?.id !== requestedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) cancelling.value = false;
    }
  }

  function clear(): void {
    refreshGeneration += 1;
    contextGeneration += 1;
    items.value = [];
    selected.value = null;
    loading.value = false;
    starting.value = false;
    cancelling.value = false;
    error.value = null;
  }

  return { items, selected, loading, starting, cancelling, error, refresh, start, refreshSelected, cancel, clear };
});
