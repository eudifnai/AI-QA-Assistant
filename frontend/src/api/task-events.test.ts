import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { createTaskEventStream, type TaskStreamEvent } from "./task-events";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  readonly protocols: string[];
  protocol = "ai-qa-task-events";
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string, protocols: string[]) {
    this.url = url;
    this.protocols = protocols;
    FakeWebSocket.instances.push(this);
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  message(event: TaskStreamEvent): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }

  close(): void {
    this.readyState = 3;
    this.onclose?.();
  }
}

function ready(streamId = "stream-1", sequence = 1): TaskStreamEvent {
  return {
    protocol_version: 1,
    stream_id: streamId,
    sequence,
    kind: "stream_ready",
    task: null,
  };
}

function updated(sequence: number): TaskStreamEvent {
  return {
    protocol_version: 1,
    stream_id: "stream-1",
    sequence,
    kind: "task_updated",
    task: {
      task_type: "analysis",
      task_id: "run-1",
      workspace_id: "workspace-1",
      status: "running",
      progress: 35,
      changed_at: "2026-08-16T06:00:00Z",
    },
  };
}

describe("task event stream", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: "desktop-session-token",
    });
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("authenticates with subprotocols and never puts the token in the URL", async () => {
    const states: string[] = [];
    const recover = vi.fn();
    const stream = createTaskEventStream({
      onEvent: vi.fn(),
      onStateChange: (state) => states.push(state),
      onRecoveryRequired: recover,
    });

    stream.start("workspace-1");
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0]!;
    expect(socket.url).toBe("ws://127.0.0.1:8765/api/workspaces/workspace-1/task-events");
    expect(socket.url).not.toContain("desktop-session-token");
    expect(socket.protocols).toEqual([
      "ai-qa-task-events",
      "auth.ZGVza3RvcC1zZXNzaW9uLXRva2Vu",
    ]);

    socket.open();
    socket.message(ready());

    expect(states).toEqual(["connecting", "connected"]);
    expect(recover).toHaveBeenCalledOnce();
  });

  it("deduplicates ordered events and requests recovery on a sequence gap", async () => {
    const received: TaskStreamEvent[] = [];
    const recover = vi.fn();
    const stream = createTaskEventStream({
      onEvent: (event) => received.push(event),
      onStateChange: vi.fn(),
      onRecoveryRequired: recover,
    });
    stream.start("workspace-1");
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0]!;
    socket.open();
    socket.message(ready());
    socket.message(updated(2));
    socket.message(updated(2));
    socket.message(updated(4));

    expect(received.map((event) => event.sequence)).toEqual([2, 4]);
    expect(recover).toHaveBeenCalledTimes(2);
  });

  it("reconnects after an unexpected close and stops permanently on request", async () => {
    vi.useFakeTimers();
    const stream = createTaskEventStream({
      onEvent: vi.fn(),
      onStateChange: vi.fn(),
      onRecoveryRequired: vi.fn(),
    });
    stream.start("workspace-1");
    await vi.runAllTicks();
    expect(FakeWebSocket.instances).toHaveLength(1);
    FakeWebSocket.instances[0]!.close();

    await vi.advanceTimersByTimeAsync(500);
    expect(FakeWebSocket.instances).toHaveLength(2);

    stream.stop();
    FakeWebSocket.instances[1]!.close();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });
});
