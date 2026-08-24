import { defineStore } from "pinia";
import { ref } from "vue";

import { listHttpEnvironments, type HttpEnvironment } from "../api/http-execution";
import { listProtoAssets, type ProtoAsset } from "../api/proto-assets";
import {
  cancelProtobufExecution,
  getProtobufExecution,
  listProtobufExecutions,
  startProtobufExecution,
  type ProtoExecution,
  type ProtoExecutionStartInput,
} from "../api/protobuf-execution";

export const useProtobufExecutionStore = defineStore("protobuf-execution", () => {
  const environments = ref<HttpEnvironment[]>([]);
  const assets = ref<ProtoAsset[]>([]);
  const runs = ref<ProtoExecution[]>([]);
  const selectedRun = ref<ProtoExecution | null>(null);
  const loading = ref(false);
  const starting = ref(false);
  const cancelling = ref(false);
  const error = ref<string | null>(null);
  let contextGeneration = 0;

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "Protobuf 执行操作失败。";
  }

  function replaceRun(run: ProtoExecution): void {
    runs.value = [run, ...runs.value.filter((item) => item.id !== run.id)];
    selectedRun.value = run;
  }

  async function refresh(workspaceId: string): Promise<void> {
    const generation = ++contextGeneration;
    loading.value = true;
    error.value = null;
    try {
      const [nextEnvironments, nextAssets, nextRuns] = await Promise.all([
        listHttpEnvironments(workspaceId), listProtoAssets(workspaceId), listProtobufExecutions(workspaceId),
      ]);
      if (generation !== contextGeneration) return;
      environments.value = nextEnvironments;
      assets.value = nextAssets;
      runs.value = nextRuns;
      selectedRun.value = nextRuns[0] ?? null;
    } catch (reason: unknown) {
      if (generation === contextGeneration) error.value = message(reason);
    } finally {
      if (generation === contextGeneration) loading.value = false;
    }
  }

  async function start(workspaceId: string, input: ProtoExecutionStartInput): Promise<void> {
    const generation = contextGeneration;
    starting.value = true;
    error.value = null;
    try {
      const run = await startProtobufExecution(workspaceId, input);
      if (generation === contextGeneration) replaceRun(run);
    } catch (reason: unknown) {
      if (generation !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) starting.value = false;
    }
  }

  async function refreshSelected(workspaceId: string): Promise<boolean> {
    if (selectedRun.value === null) return true;
    const generation = contextGeneration;
    const runId = selectedRun.value.id;
    try {
      const run = await getProtobufExecution(workspaceId, runId);
      if (generation !== contextGeneration || selectedRun.value?.id !== runId) return true;
      replaceRun(run);
      error.value = null;
      return true;
    } catch (reason: unknown) {
      if (generation !== contextGeneration || selectedRun.value?.id !== runId) return true;
      error.value = message(reason);
      return false;
    }
  }

  async function cancel(workspaceId: string): Promise<void> {
    if (selectedRun.value === null) return;
    const generation = contextGeneration;
    const runId = selectedRun.value.id;
    cancelling.value = true;
    error.value = null;
    try {
      const run = await cancelProtobufExecution(workspaceId, runId);
      if (generation === contextGeneration && selectedRun.value?.id === runId) replaceRun(run);
    } catch (reason: unknown) {
      if (generation !== contextGeneration || selectedRun.value?.id !== runId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) cancelling.value = false;
    }
  }

  function selectRun(run: ProtoExecution): void {
    selectedRun.value = run;
  }

  function clear(): void {
    contextGeneration += 1;
    environments.value = [];
    assets.value = [];
    runs.value = [];
    selectedRun.value = null;
    loading.value = false;
    starting.value = false;
    cancelling.value = false;
    error.value = null;
  }

  return { environments, assets, runs, selectedRun, loading, starting, cancelling, error, refresh, start, refreshSelected, cancel, selectRun, clear };
});
