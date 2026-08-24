import { resolveBackendConnection } from "./backend-connection";

export type TaskType =
  | "document_parse"
  | "analysis"
  | "http_execution"
  | "websocket_execution"
  | "protobuf_execution";
export type TaskStatus =
  | "pending"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "cancelled"
  | "timeout";
export type TaskEventStreamState = "stopped" | "connecting" | "connected" | "reconnecting";

export interface TaskSnapshot {
  task_type: TaskType;
  task_id: string;
  workspace_id: string;
  status: TaskStatus;
  progress: number;
  changed_at: string;
}

export interface TaskStreamEvent {
  protocol_version: 1;
  stream_id: string;
  sequence: number;
  kind: "stream_ready" | "task_updated";
  task: TaskSnapshot | null;
}

export interface TaskEventStreamCallbacks {
  onEvent: (event: TaskStreamEvent) => void;
  onStateChange: (state: TaskEventStreamState) => void;
  onRecoveryRequired: () => void;
}

export interface TaskEventStreamHandle {
  start: (workspaceId: string) => void;
  stop: () => void;
}

const TASK_EVENT_PROTOCOL = "ai-qa-task-events";
const taskTypes = new Set<TaskType>([
  "document_parse",
  "analysis",
  "http_execution",
  "websocket_execution",
  "protobuf_execution",
]);
const taskStatuses = new Set<TaskStatus>([
  "pending",
  "queued",
  "running",
  "passed",
  "failed",
  "error",
  "cancelled",
  "timeout",
]);

function encodeToken(token: string): string {
  const bytes = new TextEncoder().encode(token);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `auth.${btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
}

function isSnapshot(value: unknown): value is TaskSnapshot {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TaskSnapshot>;
  return (
    taskTypes.has(item.task_type as TaskType) &&
    typeof item.task_id === "string" &&
    item.task_id.length > 0 &&
    typeof item.workspace_id === "string" &&
    item.workspace_id.length > 0 &&
    taskStatuses.has(item.status as TaskStatus) &&
    typeof item.progress === "number" &&
    Number.isInteger(item.progress) &&
    item.progress >= 0 &&
    item.progress <= 100 &&
    typeof item.changed_at === "string" &&
    !Number.isNaN(Date.parse(item.changed_at))
  );
}

function parseEvent(value: string): TaskStreamEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const event = parsed as Partial<TaskStreamEvent>;
  if (
    event.protocol_version !== 1 ||
    typeof event.stream_id !== "string" ||
    event.stream_id.length === 0 ||
    !Number.isInteger(event.sequence) ||
    (event.sequence ?? 0) < 1
  ) {
    return null;
  }
  if (event.kind === "stream_ready" && event.task === null) return event as TaskStreamEvent;
  if (event.kind === "task_updated" && isSnapshot(event.task)) return event as TaskStreamEvent;
  return null;
}

export function createTaskEventStream(
  callbacks: TaskEventStreamCallbacks,
): TaskEventStreamHandle {
  let socket: WebSocket | null = null;
  let workspaceId: string | null = null;
  let reconnectTimer: number | null = null;
  let reconnectAttempt = 0;
  let generation = 0;
  let stopped = true;
  let streamId: string | null = null;
  let sequence = 0;
  let currentState: TaskEventStreamState = "stopped";

  function setState(state: TaskEventStreamState): void {
    if (currentState === state) return;
    currentState = state;
    callbacks.onStateChange(state);
  }

  function clearReconnectTimer(): void {
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  function scheduleReconnect(requestGeneration: number): void {
    if (stopped || requestGeneration !== generation || workspaceId === null) return;
    clearReconnectTimer();
    setState("reconnecting");
    const delay = Math.min(500 * 2 ** reconnectAttempt, 8_000);
    reconnectAttempt += 1;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      void connect(requestGeneration);
    }, delay);
  }

  async function connect(requestGeneration: number): Promise<void> {
    if (stopped || requestGeneration !== generation || workspaceId === null) return;
    try {
      const connection = await resolveBackendConnection();
      if (stopped || requestGeneration !== generation || workspaceId === null) return;
      const websocketUrl = connection.baseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
      const protocols = [TASK_EVENT_PROTOCOL];
      if (connection.token !== null) protocols.push(encodeToken(connection.token));
      const nextSocket = new WebSocket(
        `${websocketUrl}/api/workspaces/${encodeURIComponent(workspaceId)}/task-events`,
        protocols,
      );
      socket = nextSocket;
      nextSocket.onopen = () => {
        if (requestGeneration !== generation || stopped) nextSocket.close();
      };
      nextSocket.onmessage = (message) => {
        if (requestGeneration !== generation || stopped || typeof message.data !== "string") return;
        const event = parseEvent(message.data);
        if (event === null) {
          nextSocket.close(1002, "任务事件格式无效。");
          return;
        }
        if (event.kind === "stream_ready") {
          streamId = event.stream_id;
          sequence = event.sequence;
          reconnectAttempt = 0;
          setState("connected");
          callbacks.onRecoveryRequired();
          return;
        }
        if (event.stream_id !== streamId || event.sequence <= sequence) return;
        if (event.sequence !== sequence + 1) callbacks.onRecoveryRequired();
        sequence = event.sequence;
        callbacks.onEvent(event);
      };
      nextSocket.onclose = () => {
        if (socket === nextSocket) socket = null;
        scheduleReconnect(requestGeneration);
      };
      nextSocket.onerror = () => {
        // onclose owns the bounded reconnect state transition.
      };
    } catch {
      scheduleReconnect(requestGeneration);
    }
  }

  function stop(): void {
    stopped = true;
    generation += 1;
    workspaceId = null;
    streamId = null;
    sequence = 0;
    reconnectAttempt = 0;
    clearReconnectTimer();
    const current = socket;
    socket = null;
    if (current !== null && current.readyState < 2) current.close(1000, "任务事件订阅已停止。");
    setState("stopped");
  }

  function start(nextWorkspaceId: string): void {
    if (workspaceId === nextWorkspaceId && !stopped) return;
    stop();
    stopped = false;
    workspaceId = nextWorkspaceId;
    const requestGeneration = generation;
    setState("connecting");
    void connect(requestGeneration);
  }

  return { start, stop };
}
