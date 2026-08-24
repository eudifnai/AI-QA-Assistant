import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { listHttpEnvironments } from "../api/http-execution";
import { listProtoAssets } from "../api/proto-assets";
import { listProtobufExecutions, startProtobufExecution } from "../api/protobuf-execution";
import { useWorkspaceStore } from "../stores/workspaces";
import ProtobufExecutionView from "./ProtobufExecutionView.vue";

vi.mock("../api/http-execution", () => ({ listHttpEnvironments: vi.fn() }));
vi.mock("../api/proto-assets", () => ({ listProtoAssets: vi.fn() }));
vi.mock("../api/protobuf-execution", async () => {
  const actual = await vi.importActual<typeof import("../api/protobuf-execution")>("../api/protobuf-execution");
  return { ...actual, listProtobufExecutions: vi.fn(), startProtobufExecution: vi.fn(), getProtobufExecution: vi.fn(), cancelProtobufExecution: vi.fn() };
});

describe("ProtobufExecutionView", () => {
  it("starts one unary HTTP Protobuf execution with a frozen asset SHA", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useWorkspaceStore().activeWorkspaceId = "workspace-1";
    vi.mocked(listHttpEnvironments).mockResolvedValue([{
      id: "environment-1", workspace_id: "workspace-1", name: "Local", base_url: "https://api.example.com",
      variables: {}, secret_names: [], created_at: "2026-08-16T12:00:00Z", updated_at: "2026-08-16T12:00:00Z",
    }]);
    vi.mocked(listProtoAssets).mockResolvedValue([{
      id: "asset-1", workspace_id: "workspace-1", name: "echo.proto", relative_path: "echo.proto", sha256: "a".repeat(64), size_bytes: 100,
      packages: ["demo"], messages: [], enums: [], services: [{ name: "Echo", full_name: "demo.Echo", methods: [{ name: "Call", input_type: "demo.Request", output_type: "demo.Response", client_streaming: false, server_streaming: false }] }],
      created_at: "2026-08-16T12:00:00Z", updated_at: "2026-08-16T12:00:00Z",
    }]);
    vi.mocked(listProtobufExecutions).mockResolvedValue([]);
    vi.mocked(startProtobufExecution).mockResolvedValue({
      id: "run-1", workspace_id: "workspace-1", environment_id: "environment-1", environment_name: "Local",
      asset_id: "asset-1", asset_name: "echo.proto", asset_sha256: "a".repeat(64), service_name: "demo.Echo",
      method_name: "Call", base_url: "https://api.example.com", path_template: "/protobuf/echo",
      headers_template: {}, request_message_type: "demo.Request", response_message_type: "demo.Response",
      request_payload: { id: 7 }, timeout_seconds: 30, assertions: [], assertion_results: [], status: "queued",
      progress: 0, response_status_code: null, response_headers: {}, response_payload: null,
      response_size_bytes: null, duration_ms: null, error_code: null, error_message: null,
      created_at: "2026-08-16T12:00:00Z", started_at: null, finished_at: null, events: [],
    });
    const wrapper = mount(ProtobufExecutionView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    await wrapper.get('[data-testid="protobuf-request-json"]').setValue('{"id":7}');
    await wrapper.get('[data-testid="start-protobuf-execution"]').trigger("click");
    await flushPromises();

    expect(startProtobufExecution).toHaveBeenCalledWith("workspace-1", expect.objectContaining({
      environment_id: "environment-1", asset_id: "asset-1", expected_sha256: "a".repeat(64),
      service_name: "demo.Echo", method_name: "Call", request_payload: { id: 7 },
    }));
    expect(wrapper.text()).toContain("仅发送本次编码后的 Protobuf 二进制");
  });
});
