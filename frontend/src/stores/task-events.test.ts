import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaskEventStream, type TaskEventStreamCallbacks } from "../api/task-events";
import { useAnalysisStore } from "./analysis";
import { useDocumentStore } from "./documents";
import { useHttpExecutionStore } from "./http-execution";
import { useProtobufExecutionStore } from "./protobuf-execution";
import { useTaskEventStore } from "./task-events";
import { useWebSocketExecutionStore } from "./websocket-execution";

vi.mock("../api/task-events", async () => {
  const actual = await vi.importActual<typeof import("../api/task-events")>("../api/task-events");
  return { ...actual, createTaskEventStream: vi.fn() };
});

describe("task event store", () => {
  let callbacks!: TaskEventStreamCallbacks;
  const start = vi.fn();
  const stop = vi.fn();

  beforeEach(() => {
    setActivePinia(createPinia());
    start.mockReset();
    stop.mockReset();
    vi.mocked(createTaskEventStream).mockImplementation((nextCallbacks) => {
      callbacks = nextCallbacks;
      return { start, stop };
    });
  });

  it("refreshes the matching selected task and ignores another workspace", async () => {
    const analysisStore = useAnalysisStore();
    analysisStore.selected = { id: "run-1", status: "running" } as never;
    const refreshSelected = vi.spyOn(analysisStore, "refreshSelected").mockResolvedValue(true);
    const events = useTaskEventStore();

    events.start("workspace-1");
    callbacks.onEvent({
      protocol_version: 1,
      stream_id: "stream-1",
      sequence: 2,
      kind: "task_updated",
      task: {
        task_type: "analysis",
        task_id: "run-1",
        workspace_id: "workspace-1",
        status: "running",
        progress: 35,
        changed_at: "2026-08-16T06:00:00Z",
      },
    });
    callbacks.onEvent({
      protocol_version: 1,
      stream_id: "stream-1",
      sequence: 3,
      kind: "task_updated",
      task: {
        task_type: "analysis",
        task_id: "run-1",
        workspace_id: "workspace-2",
        status: "passed",
        progress: 100,
        changed_at: "2026-08-16T06:00:01Z",
      },
    });
    await Promise.resolve();

    expect(start).toHaveBeenCalledWith("workspace-1");
    expect(refreshSelected).toHaveBeenCalledOnce();
    expect(refreshSelected).toHaveBeenCalledWith("workspace-1");
  });

  it("exposes connection state and restarts cleanly for a new workspace", () => {
    const events = useTaskEventStore();
    events.start("workspace-1");
    callbacks.onStateChange("connected");
    expect(events.state).toBe("connected");

    events.start("workspace-2");
    expect(stop).toHaveBeenCalledOnce();
    expect(start).toHaveBeenLastCalledWith("workspace-2");
  });

  it("routes all supported task types to their scoped detail refresh", async () => {
    const documents = useDocumentStore();
    documents.items = [{ job: { id: "job-1", status: "running" } }] as never;
    documents.selected = { id: "document-1", job: { id: "job-1", status: "running" } } as never;
    const refreshDocuments = vi.spyOn(documents, "refresh").mockResolvedValue();
    const analysis = useAnalysisStore();
    analysis.selected = { id: "analysis-1", status: "running" } as never;
    const refreshAnalysis = vi.spyOn(analysis, "refreshSelected").mockResolvedValue(true);
    const http = useHttpExecutionStore();
    http.selectedRun = { id: "http-1", status: "running" } as never;
    const refreshHttp = vi.spyOn(http, "refreshSelected").mockResolvedValue(true);
    const websocket = useWebSocketExecutionStore();
    websocket.selectedRun = { id: "websocket-1", status: "running" } as never;
    const refreshWebSocket = vi.spyOn(websocket, "refreshSelected").mockResolvedValue(true);
    const protobuf = useProtobufExecutionStore();
    protobuf.selectedRun = { id: "protobuf-1", status: "running" } as never;
    const refreshProtobuf = vi.spyOn(protobuf, "refreshSelected").mockResolvedValue(true);
    const events = useTaskEventStore();
    events.start("workspace-1");

    const taskTypes = [
      ["document_parse", "job-1"],
      ["analysis", "analysis-1"],
      ["http_execution", "http-1"],
      ["websocket_execution", "websocket-1"],
      ["protobuf_execution", "protobuf-1"],
    ] as const;
    taskTypes.forEach(([task_type, task_id], index) =>
      callbacks.onEvent({
        protocol_version: 1,
        stream_id: "stream-1",
        sequence: index + 2,
        kind: "task_updated",
        task: {
          task_type,
          task_id,
          workspace_id: "workspace-1",
          status: "running",
          progress: 35,
          changed_at: "2026-08-16T06:00:00Z",
        },
      }),
    );

    await vi.waitFor(() => {
      expect(refreshDocuments).toHaveBeenCalledWith("workspace-1");
      expect(refreshAnalysis).toHaveBeenCalledWith("workspace-1");
      expect(refreshHttp).toHaveBeenCalledWith("workspace-1");
      expect(refreshWebSocket).toHaveBeenCalledWith("workspace-1");
      expect(refreshProtobuf).toHaveBeenCalledWith("workspace-1");
    });
  });
});
