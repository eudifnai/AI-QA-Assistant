import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { listHttpEnvironments, type HttpEnvironment } from "../api/http-execution";
import {
  cancelWebSocketExecution,
  getWebSocketExecution,
  listWebSocketExecutions,
  startWebSocketExecution,
  type WebSocketExecution,
  type WebSocketExecutionStartInput,
} from "../api/websocket-execution";

export const useWebSocketExecutionStore = defineStore("websocket-execution", () => {
  const environments = ref<HttpEnvironment[]>([]);
  const selectedEnvironmentId = ref<string | null>(null);
  const runs = ref<WebSocketExecution[]>([]);
  const selectedRun = ref<WebSocketExecution | null>(null);
  const loading = ref(false);
  const starting = ref(false);
  const cancelling = ref(false);
  const error = ref<string | null>(null);
  let contextGeneration = 0;

  const selectedEnvironment = computed(
    () => environments.value.find((item) => item.id === selectedEnvironmentId.value) ?? null,
  );

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "WebSocket 执行操作失败。";
  }

  function replaceRun(run: WebSocketExecution): void {
    runs.value = [run, ...runs.value.filter((item) => item.id !== run.id)];
    selectedRun.value = run;
  }

  async function refresh(workspaceId: string): Promise<void> {
    const requestContext = ++contextGeneration;
    loading.value = true;
    error.value = null;
    try {
      const [nextEnvironments, nextRuns] = await Promise.all([
        listHttpEnvironments(workspaceId),
        listWebSocketExecutions(workspaceId),
      ]);
      if (requestContext !== contextGeneration) return;
      environments.value = nextEnvironments;
      runs.value = nextRuns;
      selectedEnvironmentId.value = nextEnvironments[0]?.id ?? null;
      selectedRun.value = nextRuns[0] ?? null;
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
    } finally {
      if (requestContext === contextGeneration) loading.value = false;
    }
  }

  async function start(
    workspaceId: string,
    input: WebSocketExecutionStartInput,
  ): Promise<void> {
    const requestContext = contextGeneration;
    starting.value = true;
    error.value = null;
    try {
      const run = await startWebSocketExecution(workspaceId, input);
      if (requestContext !== contextGeneration) return;
      replaceRun(run);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) starting.value = false;
    }
  }

  async function refreshSelected(workspaceId: string): Promise<boolean> {
    if (selectedRun.value === null) return true;
    const requestedRunId = selectedRun.value.id;
    try {
      const run = await getWebSocketExecution(workspaceId, requestedRunId);
      if (selectedRun.value?.id !== requestedRunId) return true;
      replaceRun(run);
      error.value = null;
      return true;
    } catch (reason: unknown) {
      if (selectedRun.value?.id !== requestedRunId) return true;
      error.value = message(reason);
      return false;
    }
  }

  async function cancel(workspaceId: string): Promise<void> {
    if (selectedRun.value === null) return;
    const requestContext = contextGeneration;
    const requestedRunId = selectedRun.value.id;
    cancelling.value = true;
    error.value = null;
    try {
      const run = await cancelWebSocketExecution(workspaceId, requestedRunId);
      if (requestContext !== contextGeneration || selectedRun.value?.id !== requestedRunId) return;
      replaceRun(run);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration || selectedRun.value?.id !== requestedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) cancelling.value = false;
    }
  }

  function clear(): void {
    contextGeneration += 1;
    environments.value = [];
    selectedEnvironmentId.value = null;
    runs.value = [];
    selectedRun.value = null;
    loading.value = false;
    starting.value = false;
    cancelling.value = false;
    error.value = null;
  }

  return {
    environments,
    selectedEnvironmentId,
    selectedEnvironment,
    runs,
    selectedRun,
    loading,
    starting,
    cancelling,
    error,
    refresh,
    start,
    refreshSelected,
    cancel,
    clear,
  };
});
