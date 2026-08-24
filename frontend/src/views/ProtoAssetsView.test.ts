import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { selectProtoFile } from "../api/backend-connection";
import {
  decodeProtoMessage,
  encodeProtoMessage,
  importProtoAsset,
  listProtoAssets,
} from "../api/proto-assets";
import { useWorkspaceStore } from "../stores/workspaces";
import ProtoAssetsView from "./ProtoAssetsView.vue";

vi.mock("../api/backend-connection", async () => {
  const actual = await vi.importActual<typeof import("../api/backend-connection")>(
    "../api/backend-connection",
  );
  return { ...actual, selectProtoFile: vi.fn() };
});
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
  services: [
    {
      name: "EchoService",
      full_name: "qa.echo.EchoService",
      methods: [
        {
          name: "Echo",
          input_type: "qa.echo.EchoRequest",
          output_type: "qa.echo.EchoRequest",
          client_streaming: false,
          server_streaming: false,
        },
      ],
    },
  ],
  created_at: "2026-08-16T08:00:00Z",
  updated_at: "2026-08-16T08:00:00Z",
};

describe("ProtoAssetsView", () => {
  it("imports, summarizes, encodes and decodes one frozen Proto asset", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useWorkspaceStore().items = [
      {
        id: "workspace-1",
        name: "支付",
        path: "C:/qa/pay",
        created_at: "2026-08-16T08:00:00Z",
        last_opened_at: "2026-08-16T08:00:00Z",
      },
    ];
    useWorkspaceStore().activeWorkspaceId = "workspace-1";
    vi.mocked(listProtoAssets).mockResolvedValue([]);
    vi.mocked(selectProtoFile).mockResolvedValue("C:/qa/pay/contracts/echo.proto");
    vi.mocked(importProtoAsset).mockResolvedValue(asset);
    vi.mocked(encodeProtoMessage).mockResolvedValue({
      data_base64: "CgJoaQ==",
      size_bytes: 4,
    });
    vi.mocked(decodeProtoMessage).mockResolvedValue({
      payload: { text: "hi" },
      size_bytes: 4,
    });
    const wrapper = mount(ProtoAssetsView, {
      global: { plugins: [pinia, ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="select-proto-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="proto-json-input"]').setValue('{"text":"hi"}');
    await wrapper.get('[data-testid="encode-proto"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="decode-proto"]').trigger("click");
    await flushPromises();

    expect(importProtoAsset).toHaveBeenCalledWith(
      "workspace-1",
      "C:/qa/pay/contracts/echo.proto",
    );
    expect(encodeProtoMessage).toHaveBeenCalledWith(
      "workspace-1",
      "asset-1",
      expect.objectContaining({
        expected_sha256: "a".repeat(64),
        message_type: "qa.echo.EchoRequest",
        payload: { text: "hi" },
      }),
    );
    expect(wrapper.text()).toContain("qa.echo.EchoService");
    expect(wrapper.text()).toContain('"text": "hi"');
  });
});
