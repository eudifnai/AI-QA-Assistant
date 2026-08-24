import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import {
  deleteHttpEnvironment,
  rerunHttpExecution,
  setHttpSecret,
  startHttpExecution,
} from "./http-execution";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

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
const run = {
  id: "run-1",
  workspace_id: "workspace-1",
  environment_id: "environment-1",
  environment_name: "开发环境",
  method: "GET",
  base_url: "https://api.example.test/v1",
  path_template: "/users/{{USER_ID}}",
  headers_template: { Authorization: "Bearer {{secret.API_TOKEN}}" },
  body_template: null,
  timeout_seconds: 20,
  max_attempts: 2,
  assertions: [{ kind: "status_code", target: null, expected: "200" }],
  assertion_results: [],
  events: [],
  status: "queued",
  progress: 0,
  response_status_code: null,
  response_headers: {},
  response_body: null,
  response_body_encoding: null,
  response_size_bytes: null,
  duration_ms: null,
  error_code: null,
  error_message: null,
  created_at: "2026-08-15T01:00:00Z",
  started_at: null,
  finished_at: null,
};

describe("HTTP execution API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends a secret only to the dedicated credential endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(environment), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      setHttpSecret("workspace-1", "environment-1", "API_TOKEN", "top-secret"),
    ).resolves.toEqual(environment);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/http-environments/environment-1/secrets/API_TOKEN",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ secret: "top-secret" }) }),
    );
  });

  it("starts a queued HTTP execution with templates, not expanded secrets", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(run), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      environment_id: "environment-1",
      method: "GET" as const,
      path: "/users/{{USER_ID}}",
      headers: { Authorization: "Bearer {{secret.API_TOKEN}}" },
      body: null,
      timeout_seconds: 20,
      max_attempts: 2,
      assertions: [{ kind: "status_code" as const, target: null, expected: "200" }],
    };

    await expect(startHttpExecution("workspace-1", input)).resolves.toEqual(run);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/http-executions",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
    expect(JSON.stringify(input)).not.toContain("top-secret");
  });

  it("reruns a terminal execution through its dedicated endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(run), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(rerunHttpExecution("workspace-1", "run-1")).resolves.toEqual(run);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/http-executions/run-1/rerun",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("accepts a 204 environment deletion response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(deleteHttpEnvironment("workspace-1", "environment-1")).resolves.toBeUndefined();
  });
});
