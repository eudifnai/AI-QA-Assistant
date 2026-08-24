import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { listHttpEnvironments } from "../api/http-execution";
import {
  listWebSocketExecutions,
  startWebSocketExecution,
} from "../api/websocket-execution";
import { useWorkspaceStore } from "../stores/workspaces";
import WebSocketExecutionView from "./WebSocketExecutionView.vue";

vi.mock("../api/http-execution", async () => {
  const actual = await vi.importActual<typeof import("../api/http-execution")>(
    "../api/http-execution",
  );
  return { ...actual, listHttpEnvironments: vi.fn() };
});
vi.mock("../api/websocket-execution", async () => {
  const actual = await vi.importActual<typeof import("../api/websocket-execution")>(
    "../api/websocket-execution",
  );
  return {
    ...actual,
    listWebSocketExecutions: vi.fn(),
    startWebSocketExecution: vi.fn(),
  };
});

const environment = {
  id: "environment-1",
  workspace_id: "workspace-1",
  name: "开发环境",
  base_url: "https://api.example.test/v1",
  variables: { ROOM: "qa" },
  secret_names: ["API_TOKEN"],
  created_at: "2026-08-16T01:00:00Z",
  updated_at: "2026-08-16T01:00:00Z",
};
const passedRun = {
  id: "run-1",
  workspace_id: "workspace-1",
  environment_id: "environment-1",
  environment_name: "开发环境",
  base_url: "https://api.example.test/v1",
  path_template: "/events",
  headers_template: {},
  message_template: "hello",
  additional_message_templates: ["next"],
  receive_count: 2,
  ping_interval_seconds: 15,
  max_reconnect_attempts: 1,
  timeout_seconds: 30,
  status: "passed" as const,
  progress: 100,
  response_message: "ack qa",
  response_encoding: "text" as const,
  response_size_bytes: 23,
  duration_ms: 12,
  responses: [
    { ordinal: 1, message: "ack qa", encoding: "text" as const, size_bytes: 6 },
    { ordinal: 2, message: '{"state":"done"}', encoding: "text" as const, size_bytes: 16 },
  ],
  assertions: [
    {
      message_index: 1,
      kind: "json_path_equals" as const,
      path: "$.state",
      expected: '"done"',
    },
  ],
  assertion_results: [
    {
      message_index: 1,
      kind: "json_path_equals" as const,
      path: "$.state",
      expected: '"done"',
      actual: '"done"',
      passed: true,
      message: "断言通过。",
    },
  ],
  attempt_count: 1,
  error_code: null,
  error_message: null,
  created_at: "2026-08-16T01:00:00Z",
  started_at: "2026-08-16T01:00:00Z",
  finished_at: "2026-08-16T01:00:01Z",
  events: [
    {
      id: "event-1",
      ordinal: 1,
      level: "info" as const,
      code: "WEBSOCKET_SEQUENCE_RECEIVED",
      message: "已接收 2 条 WebSocket 消息。",
      created_at: "2026-08-16T01:00:01Z",
    },
  ],
};

describe("WebSocketExecutionView", () => {
  it("starts an ordered exchange and displays responses and assertions", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useWorkspaceStore().activeWorkspaceId = "workspace-1";
    vi.mocked(listHttpEnvironments).mockResolvedValue([environment]);
    vi.mocked(listWebSocketExecutions).mockResolvedValue([]);
    vi.mocked(startWebSocketExecution).mockResolvedValue(passedRun);
    const wrapper = mount(WebSocketExecutionView, {
      global: { plugins: [pinia, ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="websocket-message"]').setValue("hello {{ROOM}}");
    await wrapper.get('[data-testid="websocket-additional-messages"]').setValue('["next {{ROOM}}"]');
    await wrapper.get('[data-testid="websocket-receive-count"] input').setValue("2");
    await wrapper.get('[data-testid="websocket-ping-interval"] input').setValue("15");
    await wrapper.get('[data-testid="websocket-reconnect-attempts"] input').setValue("1");
    await wrapper.get('[data-testid="websocket-assertions"]').setValue(
      '[{"message_index":1,"kind":"json_path_equals","path":"$.state","expected":"\\"done\\""}]',
    );
    await wrapper.get('[data-testid="start-websocket-execution"]').trigger("click");
    await flushPromises();

    expect(startWebSocketExecution).toHaveBeenCalledWith(
      "workspace-1",
      expect.objectContaining({
        environment_id: "environment-1",
        path: "/events",
        message: "hello {{ROOM}}",
        additional_messages: ["next {{ROOM}}"],
        receive_count: 2,
        ping_interval_seconds: 15,
        max_reconnect_attempts: 1,
        assertions: [
          {
            message_index: 1,
            kind: "json_path_equals",
            path: "$.state",
            expected: '"done"',
          },
        ],
      }),
    );
    expect(wrapper.text()).toContain("wss://api.example.test/v1/events");
    expect(wrapper.text()).toContain("ack qa");
    expect(wrapper.text()).toContain('{"state":"done"}');
    expect(wrapper.text()).toContain("断言通过");
    expect(wrapper.text()).toContain("WEBSOCKET_SEQUENCE_RECEIVED");
    expect(wrapper.text()).toContain("可能产生重复副作用");
  });
});
