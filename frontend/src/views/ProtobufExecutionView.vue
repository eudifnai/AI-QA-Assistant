<script setup lang="ts">
import {
  ElAlert, ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElEmpty, ElForm, ElFormItem,
  ElInput, ElInputNumber, ElOption, ElProgress, ElSelect, ElTable, ElTableColumn,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import type { ProtoFieldAssertion } from "../api/protobuf-execution";
import { useProtobufExecutionStore } from "../stores/protobuf-execution";
import { useTaskEventStore } from "../stores/task-events";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const executionStore = useProtobufExecutionStore();
const taskEventStore = useTaskEventStore();
const { activeWorkspaceId } = storeToRefs(workspaceStore);
const { environments, assets, runs, selectedRun, loading, starting, cancelling, error } = storeToRefs(executionStore);
const { state: taskEventState, workspaceId: eventWorkspaceId } = storeToRefs(taskEventStore);

const environmentId = ref("");
const assetId = ref("");
const serviceName = ref("");
const methodName = ref("");
const path = ref("/protobuf/echo");
const headersJson = ref("{}");
const requestJson = ref("{}");
const assertionsJson = ref("[]");
const timeoutSeconds = ref(30);
const localError = ref<string | null>(null);
let pollTimer: number | null = null;

const selectedEnvironment = computed(() => environments.value.find((item) => item.id === environmentId.value) ?? null);
const selectedAsset = computed(() => assets.value.find((item) => item.id === assetId.value) ?? null);
const selectedService = computed(() => selectedAsset.value?.services.find((item) => item.full_name === serviceName.value) ?? null);
const selectedMethod = computed(() => selectedService.value?.methods.find((item) => item.name === methodName.value) ?? null);
const unaryMethods = computed(() => selectedService.value?.methods.filter((item) => !item.client_streaming && !item.server_streaming) ?? []);
const activeRun = computed(() => selectedRun.value !== null && ["pending", "queued", "running"].includes(selectedRun.value.status));
const realtimeConnected = computed(() => taskEventState.value === "connected" && eventWorkspaceId.value === activeWorkspaceId.value);
const canStart = computed(() => activeWorkspaceId.value !== null && selectedEnvironment.value !== null && selectedAsset.value !== null && selectedMethod.value !== null && !starting.value && !activeRun.value);
const endpoint = computed(() => `${selectedEnvironment.value?.base_url ?? ""}${path.value}`);
const responseJson = computed(() => selectedRun.value?.response_payload === null || selectedRun.value?.response_payload === undefined ? "" : JSON.stringify(selectedRun.value.response_payload, null, 2));

function initializeSelections(): void {
  environmentId.value = environments.value[0]?.id ?? "";
  assetId.value = assets.value[0]?.id ?? "";
  const service = assets.value[0]?.services.find((item) => item.methods.some((method) => !method.client_streaming && !method.server_streaming));
  serviceName.value = service?.full_name ?? "";
  methodName.value = service?.methods.find((item) => !item.client_streaming && !item.server_streaming)?.name ?? "";
}

function changeAsset(): void {
  const service = selectedAsset.value?.services.find((item) => item.methods.some((method) => !method.client_streaming && !method.server_streaming));
  serviceName.value = service?.full_name ?? "";
  methodName.value = service?.methods.find((item) => !item.client_streaming && !item.server_streaming)?.name ?? "";
}

function changeService(): void {
  methodName.value = unaryMethods.value[0]?.name ?? "";
}

function parseObject(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try { parsed = JSON.parse(value); } catch { throw new Error(`${label}必须是有效 JSON。`); }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error(`${label}必须是 JSON 对象。`);
  return parsed as Record<string, unknown>;
}

function parseHeaders(): Record<string, string> {
  const parsed = parseObject(headersJson.value, "请求头");
  if (!Object.values(parsed).every((value) => typeof value === "string")) throw new Error("请求头的值必须都是字符串。");
  return parsed as Record<string, string>;
}

function parseAssertions(): ProtoFieldAssertion[] {
  let parsed: unknown;
  try { parsed = JSON.parse(assertionsJson.value); } catch { throw new Error("字段断言必须是有效 JSON 数组。"); }
  if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "object" && item !== null && typeof item.path === "string" && typeof item.expected_json === "string")) {
    throw new Error("每条字段断言都必须包含 path 与 expected_json 字符串。");
  }
  return parsed as ProtoFieldAssertion[];
}

async function startExecution(): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null || selectedAsset.value === null || selectedMethod.value === null) return;
  localError.value = null;
  try {
    await executionStore.start(activeWorkspaceId.value, {
      environment_id: selectedEnvironment.value.id, asset_id: selectedAsset.value.id,
      expected_sha256: selectedAsset.value.sha256, service_name: serviceName.value,
      method_name: selectedMethod.value.name, path: path.value, headers: parseHeaders(),
      request_payload: parseObject(requestJson.value, "请求 JSON"), timeout_seconds: timeoutSeconds.value,
      assertions: parseAssertions(),
    });
    schedulePoll();
  } catch (reason: unknown) {
    if (executionStore.error === null) localError.value = reason instanceof Error ? reason.message : "Protobuf 请求启动失败。";
  }
}

async function cancelExecution(): Promise<void> {
  if (activeWorkspaceId.value === null) return;
  try { await executionStore.cancel(activeWorkspaceId.value); } catch { /* Store keeps a recoverable error. */ }
}

function schedulePoll(): void {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  if (!activeRun.value || activeWorkspaceId.value === null || realtimeConnected.value) return;
  pollTimer = window.setTimeout(async () => {
    pollTimer = null;
    if (activeWorkspaceId.value === null) return;
    if (await executionStore.refreshSelected(activeWorkspaceId.value)) schedulePoll();
  }, 1000);
}

watch(activeWorkspaceId, async (workspaceId) => {
  executionStore.clear();
  localError.value = null;
  if (workspaceId !== null) {
    await executionStore.refresh(workspaceId);
    initializeSelections();
  }
  schedulePoll();
}, { immediate: true });
watch(() => selectedRun.value?.status, schedulePoll);
watch(realtimeConnected, schedulePoll);
onBeforeUnmount(() => { if (pollTimer !== null) window.clearTimeout(pollTimer); });
</script>

<template>
  <main class="protobuf-execution-page" v-loading="loading">
    <header><p class="eyebrow">M5 · PROTOBUF RUNNER</p><h1>Protobuf 接口执行</h1><p>使用冻结描述符构造单次二进制 HTTP POST，在独立 Worker 中解码响应并校验字段。</p></header>
    <el-alert v-if="activeWorkspaceId === null" title="请先打开一个工作空间。" type="warning" :closable="false" show-icon />
    <el-alert title="仅发送本次编码后的 Protobuf 二进制与配置的请求头；不发送 .proto 源文件。当前仅支持非流式 RPC 的 HTTP/HTTPS 二进制传输，不是原生 gRPC。" type="info" :closable="false" show-icon />
    <el-alert v-if="localError || error" :title="localError ?? error ?? ''" type="error" :closable="false" />

    <section class="two-column">
      <el-card shadow="never"><template #header><h2>请求配置</h2></template>
        <el-form label-position="top">
          <el-form-item label="HTTP 环境"><el-select v-model="environmentId" style="width:100%"><el-option v-for="item in environments" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="Proto 资产"><el-select v-model="assetId" style="width:100%" @change="changeAsset"><el-option v-for="item in assets" :key="item.id" :label="`${item.name} · ${item.sha256.slice(0, 12)}`" :value="item.id" /></el-select></el-form-item>
          <el-form-item label="Service"><el-select v-model="serviceName" style="width:100%" @change="changeService"><el-option v-for="item in selectedAsset?.services ?? []" :key="item.full_name" :label="item.full_name" :value="item.full_name" /></el-select></el-form-item>
          <el-form-item label="Unary RPC"><el-select v-model="methodName" style="width:100%"><el-option v-for="item in unaryMethods" :key="item.name" :label="`${item.name}: ${item.input_type} → ${item.output_type}`" :value="item.name" /></el-select></el-form-item>
          <el-form-item label="HTTP 路径"><el-input v-model="path" /></el-form-item><p class="endpoint">目标：<code>{{ endpoint }}</code></p>
          <el-form-item label="请求头（JSON 字符串对象）"><el-input v-model="headersJson" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="请求 JSON"><el-input v-model="requestJson" data-testid="protobuf-request-json" type="textarea" :rows="7" /></el-form-item>
          <el-form-item label="字段断言（JSON 数组，expected_json 为 JSON 标量文本）"><el-input v-model="assertionsJson" type="textarea" :rows="5" placeholder='[{"path":"$.ok","expected_json":"true"}]' /></el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="timeoutSeconds" :min="1" :max="60" /></el-form-item>
          <div class="actions"><el-button data-testid="start-protobuf-execution" type="primary" :loading="starting" :disabled="!canStart" @click="startExecution">执行 Protobuf 请求</el-button><el-button v-if="activeRun" :loading="cancelling" @click="cancelExecution">取消任务</el-button></div>
        </el-form>
      </el-card>

      <el-card shadow="never"><template #header><h2>执行历史</h2></template>
        <el-progress v-if="selectedRun && activeRun" :percentage="selectedRun.progress" />
        <el-table v-if="runs.length" :data="runs" highlight-current-row @current-change="(run) => run && executionStore.selectRun(run)"><el-table-column prop="asset_name" label="资产" min-width="120" /><el-table-column prop="method_name" label="RPC" min-width="100" /><el-table-column prop="status" label="状态" width="90" /><el-table-column prop="duration_ms" label="耗时(ms)" width="100" /></el-table>
        <el-empty v-else description="尚无 Protobuf 执行记录" />
      </el-card>
    </section>

    <el-card v-if="selectedRun" shadow="never"><template #header><h2>解码结果与断言</h2></template>
      <el-descriptions :column="2" border><el-descriptions-item label="状态">{{ selectedRun.status }}</el-descriptions-item><el-descriptions-item label="HTTP 状态">{{ selectedRun.response_status_code ?? '—' }}</el-descriptions-item><el-descriptions-item label="冻结资产">{{ selectedRun.asset_name }} · {{ selectedRun.asset_sha256 }}</el-descriptions-item><el-descriptions-item label="冻结 RPC">{{ selectedRun.service_name }}/{{ selectedRun.method_name }}</el-descriptions-item><el-descriptions-item label="冻结目标" :span="2"><code>{{ selectedRun.base_url }}{{ selectedRun.path_template }}</code></el-descriptions-item></el-descriptions>
      <el-alert v-if="selectedRun.error_message" :title="`${selectedRun.error_code ?? 'PROTO_EXECUTION_FAILED'}：${selectedRun.error_message}`" type="error" :closable="false" />
      <h3>响应 JSON</h3><pre>{{ responseJson || '—' }}</pre>
      <h3>字段断言</h3><el-table v-if="selectedRun.assertion_results.length" :data="selectedRun.assertion_results"><el-table-column prop="path" label="字段路径" /><el-table-column prop="expected_json" label="预期" /><el-table-column prop="actual" label="实际" /><el-table-column prop="passed" label="通过" width="80" /></el-table><el-empty v-else description="未配置断言或尚无结果" :image-size="72" />
      <h3>安全事件</h3><el-table v-if="selectedRun.events.length" :data="selectedRun.events"><el-table-column prop="ordinal" label="#" width="60" /><el-table-column prop="code" label="事件代码" min-width="210" /><el-table-column prop="message" label="说明" min-width="220" /></el-table>
    </el-card>
  </main>
</template>

<style scoped>
.protobuf-execution-page { display:grid; gap:20px; max-width:1180px; margin:0 auto; padding:36px clamp(20px,5vw,72px) 56px; }
.two-column { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:20px; }
.actions { display:flex; gap:12px; }.eyebrow { color:#409eff; font-size:12px; font-weight:700; letter-spacing:.16em; }.endpoint { overflow-wrap:anywhere; color:var(--app-muted); }
h1,h2,h3,p { margin-top:0; } h2 { margin-bottom:0; } pre { overflow:auto; max-height:340px; padding:12px; border:1px solid var(--app-border); border-radius:8px; background:var(--app-background); white-space:pre-wrap; }
@media (max-width:800px) { .two-column { grid-template-columns:1fr; } }
</style>
