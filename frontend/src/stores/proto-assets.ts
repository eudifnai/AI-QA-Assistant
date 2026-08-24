import { defineStore } from "pinia";
import { ref } from "vue";

import {
  decodeProtoMessage,
  encodeProtoMessage,
  importProtoAsset,
  listProtoAssets,
  type ProtoAsset,
  type ProtoDecodeResult,
  type ProtoEncodeResult,
} from "../api/proto-assets";

export const useProtoAssetStore = defineStore("proto-assets", () => {
  const items = ref<ProtoAsset[]>([]);
  const selected = ref<ProtoAsset | null>(null);
  const loading = ref(false);
  const importing = ref(false);
  const coding = ref(false);
  const encoded = ref<ProtoEncodeResult | null>(null);
  const decoded = ref<ProtoDecodeResult | null>(null);
  const error = ref<string | null>(null);
  let contextGeneration = 0;

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "Proto 操作失败。";
  }

  async function refresh(workspaceId: string): Promise<void> {
    const generation = ++contextGeneration;
    loading.value = true;
    error.value = null;
    try {
      const assets = await listProtoAssets(workspaceId);
      if (generation !== contextGeneration) return;
      items.value = assets;
      selected.value = assets.find((item) => item.id === selected.value?.id) ?? assets[0] ?? null;
    } catch (reason: unknown) {
      if (generation !== contextGeneration) return;
      error.value = message(reason);
    } finally {
      if (generation === contextGeneration) loading.value = false;
    }
  }

  async function importFile(workspaceId: string, sourcePath: string): Promise<void> {
    const generation = contextGeneration;
    importing.value = true;
    error.value = null;
    try {
      const imported = await importProtoAsset(workspaceId, sourcePath);
      if (generation !== contextGeneration) return;
      items.value = [imported, ...items.value.filter((item) => item.id !== imported.id)];
      selected.value = imported;
      encoded.value = null;
      decoded.value = null;
    } catch (reason: unknown) {
      if (generation !== contextGeneration) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) importing.value = false;
    }
  }

  async function encode(
    workspaceId: string,
    asset: ProtoAsset,
    messageType: string,
    payload: Record<string, unknown>,
  ): Promise<ProtoEncodeResult> {
    const generation = contextGeneration;
    coding.value = true;
    error.value = null;
    try {
      const result = await encodeProtoMessage(workspaceId, asset.id, {
        expected_sha256: asset.sha256,
        message_type: messageType,
        payload,
      });
      if (generation !== contextGeneration) return result;
      encoded.value = result;
      decoded.value = null;
      return result;
    } catch (reason: unknown) {
      if (generation === contextGeneration) error.value = message(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) coding.value = false;
    }
  }

  async function decode(
    workspaceId: string,
    asset: ProtoAsset,
    messageType: string,
    dataBase64: string,
  ): Promise<ProtoDecodeResult> {
    const generation = contextGeneration;
    coding.value = true;
    error.value = null;
    try {
      const result = await decodeProtoMessage(workspaceId, asset.id, {
        expected_sha256: asset.sha256,
        message_type: messageType,
        data_base64: dataBase64,
      });
      if (generation !== contextGeneration) return result;
      decoded.value = result;
      return result;
    } catch (reason: unknown) {
      if (generation === contextGeneration) error.value = message(reason);
      throw reason;
    } finally {
      if (generation === contextGeneration) coding.value = false;
    }
  }

  function select(asset: ProtoAsset | null): void {
    contextGeneration += 1;
    selected.value = asset;
    encoded.value = null;
    decoded.value = null;
    coding.value = false;
    error.value = null;
  }

  function clear(): void {
    contextGeneration += 1;
    items.value = [];
    selected.value = null;
    encoded.value = null;
    decoded.value = null;
    loading.value = false;
    importing.value = false;
    coding.value = false;
    error.value = null;
  }

  return {
    items,
    selected,
    loading,
    importing,
    coding,
    encoded,
    decoded,
    error,
    refresh,
    importFile,
    encode,
    decode,
    select,
    clear,
  };
});
