import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import {
  cancelProtobufExecution,
  getProtobufExecution,
  listProtobufExecutions,
  startProtobufExecution,
} from "./protobuf-execution";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

const run = {
  id: "run-1",
  workspace_id: "workspace-1",
  environment_id: "environment-1",
  environment_name: "Local",
  asset_id: "asset-1",
  asset_name: "echo.proto",
  asset_sha256: "a".repeat(64),
  service_name: "demo.Echo",
  method_name: "Call",
  base_url: "https://api.example.com",
  path_template: "/echo",
  headers_template: {},
  request_message_type: "demo.Request",
  response_message_type: "demo.Response",
  request_payload: { id: 7 },
  timeout_seconds: 10,
  assertions: [{ path: "$.ok", expected_json: "true" }],
  assertion_results: [],
  status: "queued",
  progress: 0,
  response_status_code: null,
  response_headers: {},
  response_payload: null,
  response_size_bytes: null,
  duration_ms: null,
  error_code: null,
  error_message: null,
  created_at: "2026-08-16T12:00:00Z",
  started_at: null,
  finished_at: null,
  events: [],
};

describe("protobuf execution API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8000",
      token: "token",
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("sends a frozen asset snapshot and validates lifecycle responses", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(run), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([run]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(run), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(run), { status: 200 }));
    const input = {
      environment_id: "environment-1",
      asset_id: "asset-1",
      expected_sha256: "a".repeat(64),
      service_name: "demo.Echo",
      method_name: "Call",
      path: "/echo",
      headers: {},
      request_payload: { id: 7 },
      timeout_seconds: 10,
      assertions: [{ path: "$.ok", expected_json: "true" }],
    };

    expect(await startProtobufExecution("workspace-1", input)).toEqual(run);
    expect(await listProtobufExecutions("workspace-1")).toEqual([run]);
    expect(await getProtobufExecution("workspace-1", "run-1")).toEqual(run);
    expect(await cancelProtobufExecution("workspace-1", "run-1")).toEqual(run);
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("rejects malformed run responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...run, asset_sha256: "bad" }), { status: 200 }),
    );
    await expect(listProtobufExecutions("workspace-1")).rejects.toThrow(
      "后端 Protobuf 执行列表格式不正确",
    );
  });
});
