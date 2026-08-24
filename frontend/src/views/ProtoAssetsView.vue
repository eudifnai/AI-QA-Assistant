<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElEmpty,
  ElInput,
  ElOption,
  ElSelect,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted, ref, watch } from "vue";

import { selectProtoFile } from "../api/backend-connection";
import { useProtoAssetStore } from "../stores/proto-assets";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const protoStore = useProtoAssetStore();
const { items: workspaces, activeWorkspace } = storeToRefs(workspaceStore);
const { items, selected, loading, importing, coding, encoded, decoded, error } =
  storeToRefs(protoStore);
const workspaceId = ref("");
const messageType = ref("");
const jsonInput = ref("{}");
const base64Input = ref("");
const localError = ref<string | null>(null);

const messages = computed(() => selected.value?.messages ?? []);
const decodedJson = computed(() =>
  decoded.value === null ? "" : JSON.stringify(decoded.value.payload, null, 2),
);

watch(selected, (asset) => {
  messageType.value = asset?.messages[0]?.full_name ?? "";
  jsonInput.value = "{}";
  base64Input.value = "";
  localError.value = null;
});

async function loadWorkspace(): Promise<void> {
  localError.value = null;
  if (!workspaceId.value) {
    protoStore.clear();
    return;
  }
  await protoStore.refresh(workspaceId.value);
}

async function chooseProto(): Promise<void> {
  if (!workspaceId.value || importing.value) return;
  localError.value = null;
  try {
    const path = await selectProtoFile();
    if (path !== null) await protoStore.importFile(workspaceId.value, path);
  } catch (reason: unknown) {
    if (protoStore.error === null) {
      localError.value = reason instanceof Error ? reason.message : "无法导入 Proto 文件。";
    }
  }
}

function selectAsset(assetId: string): void {
  protoStore.select(items.value.find((item) => item.id === assetId) ?? null);
}

async function encodeMessage(): Promise<void> {
  if (!selected.value || !messageType.value || !workspaceId.value) return;
  localError.value = null;
  let payload: unknown;
  try {
    payload = JSON.parse(jsonInput.value);
  } catch {
    localError.value = "请输入有效的 JSON 对象。";
    return;
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    localError.value = "编码输入必须是 JSON 对象。";
    return;
  }
  try {
    await protoStore.encode(
      workspaceId.value,
      selected.value,
      messageType.value,
      payload as Record<string, unknown>,
    );
    base64Input.value = protoStore.encoded?.data_base64 ?? "";
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

async function decodeMessage(): Promise<void> {
  if (!selected.value || !messageType.value || !workspaceId.value || !base64Input.value) return;
  localError.value = null;
  try {
    await protoStore.decode(
      workspaceId.value,
      selected.value,
      messageType.value,
      base64Input.value,
    );
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

onMounted(async () => {
  if (workspaces.value.length === 0) await workspaceStore.refresh();
  workspaceId.value = activeWorkspace.value?.id ?? workspaces.value[0]?.id ?? "";
  await loadWorkspace();
});
</script>

<template>
  <main class="proto-page">
    <header class="proto-heading">
      <div>
        <p class="eyebrow">PROTOBUF ASSETS</p>
        <h1>Proto 资产与动态编解码</h1>
        <p>导入工作空间内的单文件定义，检查结构，并在本机完成 JSON 与 Protobuf 转换。</p>
      </div>
      <div class="proto-actions">
        <el-select
          v-model="workspaceId"
          aria-label="Proto 工作空间"
          placeholder="选择工作空间"
          @change="loadWorkspace"
        >
          <el-option
            v-for="workspace in workspaces"
            :key="workspace.id"
            :label="workspace.name"
            :value="workspace.id"
          />
        </el-select>
        <el-button
          data-testid="select-proto-file"
          type="primary"
          :disabled="!workspaceId"
          :loading="importing"
          @click="chooseProto"
        >
          选择并导入 .proto
        </el-button>
      </div>
    </header>

    <el-alert
      title="文件不会上传。当前仅支持单个 .proto 及 google/protobuf 内置类型，本地多文件 import 会明确拒绝。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="error || localError"
      :title="error ?? localError ?? ''"
      type="error"
      :closable="false"
      show-icon
    />

    <el-card shadow="never" class="asset-card">
      <template #header>已导入资产</template>
      <el-select
        v-if="items.length > 0"
        :model-value="selected?.id"
        aria-label="选择 Proto 资产"
        :loading="loading"
        @change="selectAsset"
      >
        <el-option
          v-for="asset in items"
          :key="asset.id"
          :label="`${asset.name} · ${asset.relative_path}`"
          :value="asset.id"
        />
      </el-select>
      <el-empty v-else description="尚未导入 Proto 资产" />
    </el-card>

    <template v-if="selected">
      <section class="summary-grid">
        <el-card shadow="never">
          <template #header>冻结快照</template>
          <p><strong>文件：</strong>{{ selected.relative_path }}</p>
          <p><strong>SHA-256：</strong><code>{{ selected.sha256 }}</code></p>
          <p><strong>Package：</strong>{{ selected.packages.join(", ") || "未声明" }}</p>
        </el-card>
        <el-card shadow="never">
          <template #header>Service / RPC</template>
          <el-empty v-if="selected.services.length === 0" description="未声明 service" />
          <div v-for="service in selected.services" :key="service.full_name" class="declaration">
            <strong>{{ service.full_name }}</strong>
            <p v-for="method in service.methods" :key="method.name">
              {{ method.name }}: {{ method.input_type }} → {{ method.output_type }}
            </p>
          </div>
        </el-card>
        <el-card shadow="never">
          <template #header>Message</template>
          <div v-for="message in selected.messages" :key="message.full_name" class="declaration">
            <strong>{{ message.full_name }}</strong>
            <p v-for="field in message.fields" :key="field.number">
              <el-tag size="small">{{ field.number }}</el-tag>
              {{ field.name }} · {{ field.type_name ?? field.type }} · {{ field.label }}
            </p>
          </div>
        </el-card>
        <el-card shadow="never">
          <template #header>Enum</template>
          <el-empty v-if="selected.enums.length === 0" description="未声明 enum" />
          <div v-for="item in selected.enums" :key="item.full_name" class="declaration">
            <strong>{{ item.full_name }}</strong>
            <p>{{ item.values.map((value) => `${value.name}=${value.number}`).join(", ") }}</p>
          </div>
        </el-card>
      </section>

      <el-card shadow="never" class="codec-card">
        <template #header>动态 JSON ↔ Protobuf</template>
        <el-select v-model="messageType" aria-label="选择 message" placeholder="选择 message">
          <el-option
            v-for="message in messages"
            :key="message.full_name"
            :label="message.full_name"
            :value="message.full_name"
          />
        </el-select>
        <label>
          JSON 对象
          <el-input
            v-model="jsonInput"
            data-testid="proto-json-input"
            type="textarea"
            :rows="8"
          />
        </label>
        <el-button
          data-testid="encode-proto"
          type="primary"
          :disabled="!messageType"
          :loading="coding"
          @click="encodeMessage"
        >
          编码为 Base64
        </el-button>
        <label>
          Protobuf Base64
          <el-input v-model="base64Input" type="textarea" :rows="5" />
        </label>
        <el-button
          data-testid="decode-proto"
          :disabled="!messageType || !base64Input"
          :loading="coding"
          @click="decodeMessage"
        >
          解码为 JSON
        </el-button>
        <p v-if="encoded" class="size-note">编码结果：{{ encoded.size_bytes }} 字节</p>
        <pre v-if="decodedJson">{{ decodedJson }}</pre>
      </el-card>
    </template>
  </main>
</template>

<style scoped>
.proto-page {
  display: grid;
  gap: 20px;
  padding: 32px clamp(20px, 5vw, 72px) 56px;
}

.proto-heading,
.proto-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.proto-actions {
  min-width: min(100%, 480px);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.declaration + .declaration {
  margin-top: 16px;
}

.codec-card :deep(.el-card__body) {
  display: grid;
  gap: 14px;
}

code {
  overflow-wrap: anywhere;
}

pre {
  overflow: auto;
  margin: 0;
  padding: 14px;
  border-radius: 10px;
  background: var(--app-surface-muted);
}

.eyebrow,
.size-note {
  color: var(--app-text-muted);
}

@media (max-width: 760px) {
  .proto-heading,
  .proto-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
