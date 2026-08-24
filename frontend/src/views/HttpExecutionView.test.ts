import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import {
  listHttpEnvironments,
  listHttpExecutions,
  rerunHttpExecution,
  setHttpSecret,
  startHttpExecution,
} from "../api/http-execution";
import { useHttpExecutionStore } from "../stores/http-execution";
import { useWorkspaceStore } from "../stores/workspaces";
import HttpExecutionView from "./HttpExecutionView.vue";

vi.mock("../api/http-execution", async () => {
  const actual = await vi.importActual<typeof import("../api/http-execution")>(
    "../api/http-execution",
  );
  return {
    ...actual,
    listHttpEnvironments: vi.fn(),
    listHttpExecutions: vi.fn(),
    rerunHttpExecution: vi.fn(),
    setHttpSecret: vi.fn(),
    startHttpExecution: vi.fn(),
  };
});

const environment = {
  id: "environment-1",
  workspace_id: "workspace-1",
  name: "开发环境",
  base_url: "https://api.example.test/v1",
  variables: { USER_ID: "42" },
  secret_names: ["API_TOKEN"],
  created_at: "2026-08-15T01:00:00Z",
  updated_at: "2026-08-15T01:00:00Z",
};
const passedRun = {
  id: "run-1",
  workspace_id: "workspace-1",
  environment_id: "environment-1",
  environment_name: "开发环境",
  method: "GET" as const,
  base_url: "https://api.example.test/v1",
  path_template: "/health",
  headers_template: {},
  body_template: null,
  timeout_seconds: 30,
  max_attempts: 1,
  assertions: [{ kind: "status_code" as const, target: null, expected: "200" }],
  assertion_results: [
    {
      kind: "status_code" as const,
      target: null,
      expected: "200",
      actual: "200",
      passed: true,
      message: "HTTP 状态码符合预期。",
    },
  ],
  events: [
    {
      id: "event-1",
      ordinal: 1,
      level: "info" as const,
      code: "HTTP_EXECUTION_ASSERTIONS_PASSED",
      message: "全部响应断言通过。",
      attempt: 1,
      created_at: "2026-08-15T01:00:01Z",
    },
  ],
  status: "passed" as const,
  progress: 100,
  response_status_code: 200,
  response_headers: { "Content-Type": "application/json" },
  response_body: '{"ok":true}',
  response_body_encoding: "text" as const,
  response_size_bytes: 11,
  duration_ms: 12,
  error_code: null,
  error_message: null,
  created_at: "2026-08-15T01:00:00Z",
  started_at: "2026-08-15T01:00:00Z",
  finished_at: "2026-08-15T01:00:01Z",
};

describe("HttpExecutionView", () => {
  it("clears the secret input and keeps the value out of Pinia state", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useWorkspaceStore().activeWorkspaceId = "workspace-1";
    vi.mocked(listHttpEnvironments).mockResolvedValue([environment]);
    vi.mocked(listHttpExecutions).mockResolvedValue([]);
    vi.mocked(setHttpSecret).mockResolvedValue(environment);
    vi.mocked(startHttpExecution).mockResolvedValue(passedRun);
    vi.mocked(rerunHttpExecution).mockResolvedValue({ ...passedRun, id: "run-2" });
    const wrapper = mount(HttpExecutionView, { global: { plugins: [pinia, ElementPlus] } });
    await flushPromises();

    await wrapper.get('input[placeholder="API_TOKEN"]').setValue("API_TOKEN");
    const secretInput = wrapper.get('[data-testid="http-secret-value"]');
    await secretInput.setValue("top-secret");
    await wrapper.get('[data-testid="save-http-secret"]').trigger("click");
    await flushPromises();

    expect(setHttpSecret).toHaveBeenCalledWith(
      "workspace-1",
      "environment-1",
      "API_TOKEN",
      "top-secret",
    );
    expect((secretInput.element as HTMLInputElement).value).toBe("");
    expect(JSON.stringify(useHttpExecutionStore().$state)).not.toContain("top-secret");

    await wrapper.get('[data-testid="start-http-execution"]').trigger("click");
    await flushPromises();
    expect(startHttpExecution).toHaveBeenCalledWith(
      "workspace-1",
      expect.objectContaining({
        environment_id: "environment-1",
        path: "/health",
        max_attempts: 1,
        assertions: [{ kind: "status_code", target: null, expected: "200" }],
      }),
    );
    expect(wrapper.text()).toContain("200");
    expect(wrapper.text()).toContain('{"ok":true}');
    expect(wrapper.text()).toContain("HTTP 状态码符合预期");
    expect(wrapper.text()).toContain("HTTP_EXECUTION_ASSERTIONS_PASSED");

    await wrapper.get('[data-testid="rerun-http-execution"]').trigger("click");
    await flushPromises();
    expect(rerunHttpExecution).toHaveBeenCalledWith("workspace-1", "run-1");
  });
});
