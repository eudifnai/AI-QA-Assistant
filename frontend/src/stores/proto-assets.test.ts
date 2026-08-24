import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { encodeProtoMessage, importProtoAsset } from "../api/proto-assets";
import { useProtoAssetStore } from "./proto-assets";

vi.mock("../api/proto-assets", async () => {
  const actual = await vi.importActual<typeof import("../api/proto-assets")>(
    "../api/proto-assets",
  );
  return {
    ...actual,
    listProtoAssets: vi.fn(),
    importProtoAsset: vi.fn(),
    encodeProtoMessage: vi.fn(),
    decodeProtoMessage: vi.fn(),
  };
});

const asset = {
  id: "asset-1",
  workspace_id: "workspace-1",
  name: "echo.proto",
  relative_path: "echo.proto",
  sha256: "a".repeat(64),
  size_bytes: 64,
  packages: ["qa.echo"],
  messages: [],
  enums: [],
  services: [],
  created_at: "2026-08-16T08:00:00Z",
  updated_at: "2026-08-16T08:00:00Z",
};

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

describe("Proto asset store context isolation", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("ignores an import response that arrives after the workspace is cleared", async () => {
    const pending = deferred<typeof asset>();
    vi.mocked(importProtoAsset).mockReturnValue(pending.promise);
    const store = useProtoAssetStore();

    const importing = store.importFile("workspace-1", "C:/qa/echo.proto");
    store.clear();
    pending.resolve(asset);
    await importing;

    expect(store.items).toEqual([]);
    expect(store.selected).toBeNull();
    expect(store.error).toBeNull();
  });

  it("ignores an encode response that arrives after the context is cleared", async () => {
    const pending = deferred<{ data_base64: string; size_bytes: number }>();
    vi.mocked(encodeProtoMessage).mockReturnValue(pending.promise);
    const store = useProtoAssetStore();

    const encoding = store.encode("workspace-1", asset, "qa.echo.Echo", {});
    store.clear();
    pending.resolve({ data_base64: "", size_bytes: 0 });
    await encoding;

    expect(store.encoded).toBeNull();
    expect(store.error).toBeNull();
  });
});
