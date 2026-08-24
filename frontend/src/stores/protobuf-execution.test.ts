import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listHttpEnvironments } from "../api/http-execution";
import { listProtoAssets } from "../api/proto-assets";
import { startProtobufExecution } from "../api/protobuf-execution";
import { useProtobufExecutionStore } from "./protobuf-execution";

vi.mock("../api/http-execution", () => ({ listHttpEnvironments: vi.fn() }));
vi.mock("../api/proto-assets", () => ({ listProtoAssets: vi.fn() }));
vi.mock("../api/protobuf-execution", async () => {
  const actual = await vi.importActual<typeof import("../api/protobuf-execution")>("../api/protobuf-execution");
  return { ...actual, listProtobufExecutions: vi.fn().mockResolvedValue([]), startProtobufExecution: vi.fn(), getProtobufExecution: vi.fn(), cancelProtobufExecution: vi.fn() };
});

describe("Protobuf execution store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(listHttpEnvironments).mockResolvedValue([]);
    vi.mocked(listProtoAssets).mockResolvedValue([]);
  });

  it("loads environments, assets and runs into one workspace context", async () => {
    const store = useProtobufExecutionStore();
    await store.refresh("workspace-1");
    expect(listHttpEnvironments).toHaveBeenCalledWith("workspace-1");
    expect(listProtoAssets).toHaveBeenCalledWith("workspace-1");
    expect(store.loading).toBe(false);
  });

  it("ignores a start response after clear", async () => {
    let resolve!: (value: never) => void;
    vi.mocked(startProtobufExecution).mockReturnValue(new Promise((done) => { resolve = done; }));
    const store = useProtobufExecutionStore();
    const starting = store.start("workspace-1", {
      environment_id: "environment-1", asset_id: "asset-1", expected_sha256: "a".repeat(64),
      service_name: "demo.Echo", method_name: "Call", path: "/echo", headers: {}, request_payload: {},
      timeout_seconds: 10, assertions: [],
    });
    store.clear();
    resolve({ id: "late" } as never);
    await starting;
    expect(store.runs).toEqual([]);
    expect(store.starting).toBe(false);
  });
});
