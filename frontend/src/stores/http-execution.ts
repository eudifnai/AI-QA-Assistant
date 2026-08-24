import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  cancelHttpExecution,
  createHttpEnvironment,
  deleteHttpEnvironment,
  deleteHttpSecret,
  getHttpExecution,
  listHttpEnvironments,
  listHttpExecutions,
  rerunHttpExecution,
  setHttpSecret,
  startHttpExecution,
  updateHttpEnvironment,
  type HttpEnvironment,
  type HttpEnvironmentInput,
  type HttpExecution,
  type HttpExecutionStartInput,
} from "../api/http-execution";

export const useHttpExecutionStore = defineStore("http-execution", () => {
  const environments = ref<HttpEnvironment[]>([]);
  const selectedEnvironmentId = ref<string | null>(null);
  const runs = ref<HttpExecution[]>([]);
  const selectedRun = ref<HttpExecution | null>(null);
  const loading = ref(false);
  const savingEnvironment = ref(false);
  const savingSecret = ref(false);
  const starting = ref(false);
  const cancelling = ref(false);
  const rerunning = ref(false);
  const error = ref<string | null>(null);
  let contextGeneration = 0;

  const selectedEnvironment = computed(
    () => environments.value.find((item) => item.id === selectedEnvironmentId.value) ?? null,
  );

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "HTTP 执行操作失败。";
  }

  function replaceEnvironment(environment: HttpEnvironment): void {
    environments.value = [
      environment,
      ...environments.value.filter((item) => item.id !== environment.id),
    ];
    selectedEnvironmentId.value = environment.id;
  }

  function replaceRun(run: HttpExecution): void {
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
        listHttpExecutions(workspaceId),
      ]);
      if (requestContext !== contextGeneration) return;
      environments.value = nextEnvironments;
      runs.value = nextRuns;
      if (!nextEnvironments.some((item) => item.id === selectedEnvironmentId.value)) {
        selectedEnvironmentId.value = nextEnvironments[0]?.id ?? null;
      }
      selectedRun.value =
        nextRuns.find((item) => item.id === selectedRun.value?.id) ?? nextRuns[0] ?? null;
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
    } finally {
      if (requestContext === contextGeneration) loading.value = false;
    }
  }

  async function saveEnvironment(
    workspaceId: string,
    input: HttpEnvironmentInput,
    environmentId: string | null = null,
  ): Promise<void> {
    const requestContext = contextGeneration;
    savingEnvironment.value = true;
    error.value = null;
    try {
      const saved =
        environmentId === null
          ? await createHttpEnvironment(workspaceId, input)
          : await updateHttpEnvironment(workspaceId, environmentId, input);
      if (requestContext !== contextGeneration) return;
      replaceEnvironment(saved);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) savingEnvironment.value = false;
    }
  }

  async function removeEnvironment(workspaceId: string, environmentId: string): Promise<void> {
    const requestContext = contextGeneration;
    error.value = null;
    try {
      await deleteHttpEnvironment(workspaceId, environmentId);
      if (requestContext !== contextGeneration) return;
      environments.value = environments.value.filter((item) => item.id !== environmentId);
      if (selectedEnvironmentId.value === environmentId) {
        selectedEnvironmentId.value = environments.value[0]?.id ?? null;
      }
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    }
  }

  async function saveSecret(
    workspaceId: string,
    environmentId: string,
    name: string,
    secret: string,
  ): Promise<void> {
    const requestContext = contextGeneration;
    savingSecret.value = true;
    error.value = null;
    try {
      const updated = await setHttpSecret(workspaceId, environmentId, name, secret);
      if (requestContext !== contextGeneration) return;
      replaceEnvironment(updated);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) savingSecret.value = false;
    }
  }

  async function removeSecret(
    workspaceId: string,
    environmentId: string,
    name: string,
  ): Promise<void> {
    const requestContext = contextGeneration;
    error.value = null;
    try {
      const updated = await deleteHttpSecret(workspaceId, environmentId, name);
      if (requestContext !== contextGeneration) return;
      replaceEnvironment(updated);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    }
  }

  async function start(workspaceId: string, input: HttpExecutionStartInput): Promise<void> {
    const requestContext = contextGeneration;
    starting.value = true;
    error.value = null;
    try {
      const run = await startHttpExecution(workspaceId, input);
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
      const run = await getHttpExecution(workspaceId, requestedRunId);
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
      const run = await cancelHttpExecution(workspaceId, requestedRunId);
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

  async function rerun(workspaceId: string): Promise<void> {
    if (selectedRun.value === null) return;
    const requestContext = contextGeneration;
    const requestedRunId = selectedRun.value.id;
    rerunning.value = true;
    error.value = null;
    try {
      const run = await rerunHttpExecution(workspaceId, requestedRunId);
      if (requestContext !== contextGeneration || selectedRun.value?.id !== requestedRunId) return;
      replaceRun(run);
    } catch (reason: unknown) {
      if (requestContext !== contextGeneration || selectedRun.value?.id !== requestedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestContext === contextGeneration) rerunning.value = false;
    }
  }

  function clear(): void {
    contextGeneration += 1;
    environments.value = [];
    selectedEnvironmentId.value = null;
    runs.value = [];
    selectedRun.value = null;
    loading.value = false;
    savingEnvironment.value = false;
    savingSecret.value = false;
    starting.value = false;
    cancelling.value = false;
    rerunning.value = false;
    error.value = null;
  }

  return {
    environments,
    selectedEnvironmentId,
    selectedEnvironment,
    runs,
    selectedRun,
    loading,
    savingEnvironment,
    savingSecret,
    starting,
    cancelling,
    rerunning,
    error,
    refresh,
    saveEnvironment,
    removeEnvironment,
    saveSecret,
    removeSecret,
    start,
    refreshSelected,
    cancel,
    rerun,
    clear,
  };
});
