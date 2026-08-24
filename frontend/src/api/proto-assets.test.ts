import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveBackendConnection } from "./backend-connection";
import { encodeProtoMessage, importProtoAsset } from "./proto-assets";

vi.mock("./backend-connection", () => ({ resolveBackendConnection: vi.fn() }));

const asset = {
  id: "asset-1",
  workspace_id: "workspace-1",
  name: "echo.proto",
  relative_path: "contracts/echo.proto",
  sha256: "a".repeat(64),
  size_bytes: 128,
  packages: ["qa.echo"],
  messages: [
    {
      name: "EchoRequest",
      full_name: "qa.echo.EchoRequest",
      fields: [
        {
          name: "text",
          number: 1,
          type: "TYPE_STRING",
          label: "LABEL_OPTIONAL",
          type_name: null,
        },
      ],
    },
  ],
  enums: [],
  services: [],
  created_at: "2026-08-16T08:00:00Z",
  updated_at: "2026-08-16T08:00:00Z",
};

describe("Proto assets API", () => {
  beforeEach(() => {
    vi.mocked(resolveBackendConnection).mockResolvedValue({
      baseUrl: "http://127.0.0.1:8765",
      token: null,
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("imports a local path without sending file contents", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(asset), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      importProtoAsset("workspace-1", "C:\\qa\\workspace\\contracts\\echo.proto"),
    ).resolves.toEqual(asset);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/proto-assets",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source_path: "C:\\qa\\workspace\\contracts\\echo.proto",
        }),
      }),
    );
  });

  it("encodes against the exact descriptor snapshot", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data_base64: "CgJoaQ==", size_bytes: 4 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      expected_sha256: "a".repeat(64),
      message_type: "qa.echo.EchoRequest",
      payload: { text: "hi" },
    };

    await expect(encodeProtoMessage("workspace-1", "asset-1", input)).resolves.toEqual({
      data_base64: "CgJoaQ==",
      size_bytes: 4,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/workspaces/workspace-1/proto-assets/asset-1/encode",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });
});
