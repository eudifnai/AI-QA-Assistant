import { defineStore } from "pinia";
import { ref } from "vue";

import {
  createTaskEventStream,
  type TaskEventStreamHandle,
  type TaskEventStreamState,
  type TaskStreamEvent,
} from "../api/task-events";
import { useAnalysisStore } from "./analysis";
import { useDocumentStore } from "./documents";
import { useHttpExecutionStore } from "./http-execution";
import { useProtobufExecutionStore } from "./protobuf-execution";
import { useWebSocketExecutionStore } from "./websocket-execution";

const activeStatuses = new Set(["pending", "queued", "running"]);

export const useTaskEventStore = defineStore("task-events", () => {
  const state = ref<TaskEventStreamState>("stopped");
  const workspaceId = ref<string | null>(null);
  let stream: TaskEventStreamHandle | null = null;

  async function refreshDocumentTask(currentWorkspaceId: string, taskId: string): Promise<void> {
    const documents = useDocumentStore();
    if (!documents.items.some((item) => item.job.id === taskId)) return;
    await documents.refresh(currentWorkspaceId);
    if (documents.selected?.job.status === "passed") {
      await documents.loadChunks(currentWorkspaceId, documents.selected.id);
    }
  }

  async function handleEvent(event: TaskStreamEvent): Promise<void> {
    const task = event.task;
    const currentWorkspaceId = workspaceId.value;
    if (task === null || currentWorkspaceId === null || task.workspace_id !== currentWorkspaceId) {
      return;
    }
    if (task.task_type === "document_parse") {
      await refreshDocumentTask(currentWorkspaceId, task.task_id);
      return;
    }
    if (task.task_type === "analysis") {
      const store = useAnalysisStore();
      if (store.selected?.id === task.task_id) await store.refreshSelected(currentWorkspaceId);
      return;
    }
    if (task.task_type === "http_execution") {
      const store = useHttpExecutionStore();
      if (store.selectedRun?.id === task.task_id) await store.refreshSelected(currentWorkspaceId);
      return;
    }
    if (task.task_type === "websocket_execution") {
      const store = useWebSocketExecutionStore();
      if (store.selectedRun?.id === task.task_id) await store.refreshSelected(currentWorkspaceId);
      return;
    }
    const store = useProtobufExecutionStore();
    if (store.selectedRun?.id === task.task_id) await store.refreshSelected(currentWorkspaceId);
  }

  async function recoverCurrentTasks(): Promise<void> {
    const currentWorkspaceId = workspaceId.value;
    if (currentWorkspaceId === null) return;
    const documents = useDocumentStore();
    if (documents.items.some((item) => activeStatuses.has(item.job.status))) {
      await documents.refresh(currentWorkspaceId);
      if (documents.selected?.job.status === "passed") {
        await documents.loadChunks(currentWorkspaceId, documents.selected.id);
      }
    }
    const analysis = useAnalysisStore();
    if (analysis.selected && activeStatuses.has(analysis.selected.status)) {
      await analysis.refreshSelected(currentWorkspaceId);
    }
    const http = useHttpExecutionStore();
    if (http.selectedRun && activeStatuses.has(http.selectedRun.status)) {
      await http.refreshSelected(currentWorkspaceId);
    }
    const websocket = useWebSocketExecutionStore();
    if (websocket.selectedRun && activeStatuses.has(websocket.selectedRun.status)) {
      await websocket.refreshSelected(currentWorkspaceId);
    }
    const protobuf = useProtobufExecutionStore();
    if (protobuf.selectedRun && activeStatuses.has(protobuf.selectedRun.status)) {
      await protobuf.refreshSelected(currentWorkspaceId);
    }
  }

  function ensureStream(): TaskEventStreamHandle {
    stream ??= createTaskEventStream({
      onEvent: (event) => void handleEvent(event),
      onStateChange: (nextState) => {
        state.value = nextState;
      },
      onRecoveryRequired: () => void recoverCurrentTasks(),
    });
    return stream;
  }

  function start(nextWorkspaceId: string): void {
    if (workspaceId.value === nextWorkspaceId && state.value !== "stopped") return;
    if (workspaceId.value !== null) ensureStream().stop();
    workspaceId.value = nextWorkspaceId;
    ensureStream().start(nextWorkspaceId);
  }

  function stop(): void {
    stream?.stop();
    workspaceId.value = null;
    state.value = "stopped";
  }

  return { state, workspaceId, start, stop };
});
