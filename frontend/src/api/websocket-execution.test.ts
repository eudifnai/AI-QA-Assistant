import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { startWebSocketExecution } from "./websocket-execution";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

const run = {
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
  timeout_seconds: 10,
  status: "queued",
  progress: 0,
  response_message: null,
  response_encoding: null,
  response_size_bytes: null,
  duration_ms: null,
  responses: [],
  assertions: [
    { message_index: 1, kind: "text_contains", path: null, expected: "done" },
  ],
  assertion_results: [],
  attempt_count: 1,
  error_code: null,
  error_message: null,
  created_at: "2026-08-16T01:00:00Z",
  started_at: null,
  finished_at: null,
  events: [],
};

describe("WebSocket execution API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("starts with templates and no expanded secret", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(run), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      environment_id: "environment-1",
      path: "/events",
      headers: { Authorization: "Bearer {{secret.API_TOKEN}}" },
      message: "hello",
      additional_messages: ["next"],
      receive_count: 2,
      ping_interval_seconds: 15,
      max_reconnect_attempts: 1,
      assertions: [
        { message_index: 1, kind: "text_contains" as const, path: null, expected: "done" },
      ],
      timeout_seconds: 10,
    };

    await expect(startWebSocketExecution("workspace-1", input)).resolves.toEqual(run);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/websocket-executions",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
    expect(JSON.stringify(input)).not.toContain("top-secret");
  });
});
