<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElProgress,
  ElSelect,
  ElTable,
  ElTableColumn,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import type { WebSocketMessageAssertion } from "../api/websocket-execution";
import { useTaskEventStore } from "../stores/task-events";
import { useWebSocketExecutionStore } from "../stores/websocket-execution";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const executionStore = useWebSocketExecutionStore();
const taskEventStore = useTaskEventStore();
const { activeWorkspaceId } = storeToRefs(workspaceStore);
const {
  environments,
  selectedEnvironmentId,
  selectedEnvironment,
  runs,
  selectedRun,
  loading,
  starting,
  cancelling,
  error,
} = storeToRefs(executionStore);
const { state: taskEventState, workspaceId: eventWorkspaceId } = storeToRefs(taskEventStore);

const path = ref("/events");
const headersJson = ref("{}");
const message = ref('{"action":"subscribe"}');
const additionalMessagesJson = ref("[]");
const receiveCount = ref(1);
const pingIntervalSeconds = ref(0);
const maxReconnectAttempts = ref(0);
const assertionsJson = ref("[]");
const timeoutSeconds = ref(30);
const localError = ref<string | null>(null);
let pollTimer: number | null = null;

const activeRun = computed(
  () => selectedRun.value !== null && ["pending", "queued", "running"].includes(selectedRun.value.status),
);
const realtimeConnected = computed(
  () =>
    taskEventState.value === "connected" && eventWorkspaceId.value === activeWorkspaceId.value,
);
const canStart = computed(
  () =>
    activeWorkspaceId.value !== null &&
    selectedEnvironment.value !== null &&
    message.value.length > 0 &&
    (pingIntervalSeconds.value === 0 || pingIntervalSeconds.value >= 5) &&
    !starting.value &&
    !activeRun.value,
);
const endpoint = computed(() => {
  const base = selectedEnvironment.value?.base_url ?? "";
  const websocketBase = base.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
  return `${websocketBase}${path.value}`;
});

function parseHeaders(value: string): Record<string, string> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("握手请求头必须是 JSON 对象。");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Object.values(parsed).every((item) => typeof item === "string")
  ) {
    throw new Error("握手请求头的键和值都必须是字符串。");
  }
  return parsed as Record<string, string>;
}

function parseStringArray(value: string): string[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("追加消息必须是 JSON 字符串数组。");
  }
  if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "string")) {
    throw new Error("追加消息必须是 JSON 字符串数组。");
  }
  if (parsed.length > 9) throw new Error("一次最多发送 10 条消息（含首条消息）。");
  if (parsed.some((item) => item.length === 0)) throw new Error("发送消息不能为空。");
  return parsed;
}

function parseAssertions(value: string): WebSocketMessageAssertion[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("消息断言必须是 JSON 数组。");
  }
  if (!Array.isArray(parsed) || parsed.length > 20) {
    throw new Error("消息断言必须是最多 20 项的 JSON 数组。");
  }
  const kinds = new Set(["encoding", "text_equals", "text_contains", "json_path_equals"]);
  if (
    !parsed.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        Number.isInteger((item as WebSocketMessageAssertion).message_index) &&
        kinds.has((item as WebSocketMessageAssertion).kind) &&
        ((item as WebSocketMessageAssertion).path === null ||
          typeof (item as WebSocketMessageAssertion).path === "string") &&
        typeof (item as WebSocketMessageAssertion).expected === "string",
    )
  ) {
    throw new Error("消息断言格式不正确。");
  }
  const assertions = parsed as WebSocketMessageAssertion[];
  for (const assertion of assertions) {
    if (assertion.message_index < 0 || assertion.message_index >= receiveCount.value) {
      throw new Error("消息断言索引必须落在本次接收范围内。");
    }
    if (assertion.kind === "encoding") {
      if (assertion.path !== null || !["text", "base64"].includes(assertion.expected)) {
        throw new Error("编码断言只接受 text 或 base64，且 path 必须为 null。");
      }
    } else if (assertion.kind === "text_equals" || assertion.kind === "text_contains") {
      if (assertion.path !== null) throw new Error("文本断言的 path 必须为 null。");
    } else {
      if (assertion.path === null || !/^\$(?:\.(?:[A-Za-z_][A-Za-z0-9_-]*|\d+))+$/.test(assertion.path)) {
        throw new Error("JSON 路径断言必须使用 $.field 形式的路径。");
      }
      try {
        const expected: unknown = JSON.parse(assertion.expected);
        if (typeof expected === "object" && expected !== null) throw new Error();
      } catch {
        throw new Error("JSON 路径断言的 expected 必须是 JSON 标量文本。");
      }
    }
  }
  return assertions;
}

async function startExecution(): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null) return;
  localError.value = null;
  try {
    await executionStore.start(activeWorkspaceId.value, {
      environment_id: selectedEnvironment.value.id,
      path: path.value,
      headers: parseHeaders(headersJson.value),
      message: message.value,
      additional_messages: parseStringArray(additionalMessagesJson.value),
      receive_count: receiveCount.value,
      ping_interval_seconds: pingIntervalSeconds.value === 0 ? null : pingIntervalSeconds.value,
      max_reconnect_attempts: maxReconnectAttempts.value,
      assertions: parseAssertions(assertionsJson.value),
      timeout_seconds: timeoutSeconds.value,
    });
    schedulePoll();
  } catch (reason: unknown) {
    localError.value = reason instanceof Error ? reason.message : "WebSocket 请求启动失败。";
  }
}

async function cancelExecution(): Promise<void> {
  if (activeWorkspaceId.value === null) return;
  try {
    await executionStore.cancel(activeWorkspaceId.value);
  } catch {
    // Store error remains visible and recoverable.
  }
}

function schedulePoll(): void {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  if (!activeRun.value || activeWorkspaceId.value === null || realtimeConnected.value) return;
  pollTimer = window.setTimeout(async () => {
    pollTimer = null;
    if (activeWorkspaceId.value === null) return;
    const ok = await executionStore.refreshSelected(activeWorkspaceId.value);
    if (ok) schedulePoll();
  }, 1000);
}

function selectRun(run: unknown): void {
  selectedRun.value = run as typeof selectedRun.value;
  schedulePoll();
}

watch(
  activeWorkspaceId,
  async (workspaceId) => {
    executionStore.clear();
    localError.value = null;
    if (workspaceId !== null) await executionStore.refresh(workspaceId);
    schedulePoll();
  },
  { immediate: true },
);
watch(() => selectedRun.value?.status, schedulePoll);
watch(realtimeConnected, schedulePoll);
onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <main class="execution-page" v-loading="loading">
    <header class="page-heading">
      <div>
        <p class="eyebrow">M5 · WEBSOCKET RUNNER</p>
        <h1>WebSocket 序列执行</h1>
        <p>在独立 Worker 中按序发送最多 10 条消息、接收最多 20 条消息，并验证有序响应。</p>
      </div>
    </header>

    <el-alert
      v-if="activeWorkspaceId === null"
      title="请先在工作空间页面打开一个工作空间。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      title="HTTP/HTTPS 环境会分别映射为 ws/wss。安全变量只在 Worker 中展开，连接不使用系统代理。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      title="启用自动重连后会重放完整发送序列，可能产生重复副作用；仅对连接超时或不可用重连一次。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="localError || error" :title="localError ?? error ?? ''" type="error" :closable="false" />

    <section class="two-column">
      <el-card shadow="never">
        <template #header><h2>连接与消息</h2></template>
        <el-form label-position="top">
          <el-form-item label="环境">
            <el-select v-model="selectedEnvironmentId" placeholder="请先在 HTTP 执行页创建环境" style="width: 100%">
              <el-option v-for="item in environments" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="WebSocket 路径">
            <el-input v-model="path" placeholder="/events" />
          </el-form-item>
          <p class="endpoint-preview">目标：<code>{{ endpoint }}</code></p>
          <el-form-item label="握手请求头（JSON 字符串对象）">
            <el-input v-model="headersJson" type="textarea" :rows="5" />
          </el-form-item>
          <el-form-item label="第 1 条发送消息（可使用变量引用）">
            <el-input v-model="message" data-testid="websocket-message" type="textarea" :rows="8" />
          </el-form-item>
          <el-form-item label="追加发送消息（JSON 字符串数组，最多 9 条）">
            <el-input
              v-model="additionalMessagesJson"
              data-testid="websocket-additional-messages"
              type="textarea"
              :rows="5"
              placeholder='["next {{ROOM}}"]'
            />
          </el-form-item>
          <el-form-item label="接收消息数（1–20）">
            <el-input-number
              v-model="receiveCount"
              data-testid="websocket-receive-count"
              :min="1"
              :max="20"
            />
          </el-form-item>
          <el-form-item label="Ping 心跳间隔（秒，0 表示关闭）">
            <el-input-number
              v-model="pingIntervalSeconds"
              data-testid="websocket-ping-interval"
              :min="0"
              :max="60"
              :step="5"
            />
            <p class="field-help">启用时允许 5–60 秒。</p>
          </el-form-item>
          <el-form-item label="连接失败自动重连次数（0–1）">
            <el-input-number
              v-model="maxReconnectAttempts"
              data-testid="websocket-reconnect-attempts"
              :min="0"
              :max="1"
            />
          </el-form-item>
          <el-form-item label="有序消息断言（JSON 数组，message_index 从 0 开始）">
            <el-input
              v-model="assertionsJson"
              data-testid="websocket-assertions"
              type="textarea"
              :rows="6"
              placeholder='[{"message_index":0,"kind":"text_contains","path":null,"expected":"ok"}]'
            />
            <p class="field-help">
              支持 encoding、text_equals、text_contains、json_path_equals；JSON 期望值填写序列化标量，
              例如字符串写为 &quot;\&quot;done\&quot;&quot;。
            </p>
          </el-form-item>
          <el-form-item label="连接与接收超时（秒）">
            <el-input-number v-model="timeoutSeconds" :min="1" :max="60" />
          </el-form-item>
          <div class="actions">
            <el-button
              data-testid="start-websocket-execution"
              type="primary"
              :loading="starting"
              :disabled="!canStart"
              @click="startExecution"
            >执行消息序列</el-button>
            <el-button v-if="activeRun" :loading="cancelling" @click="cancelExecution">取消任务</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header><h2>执行历史</h2></template>
        <el-progress v-if="selectedRun && activeRun" :percentage="selectedRun.progress" />
        <el-table v-if="runs.length" :data="runs" highlight-current-row @current-change="selectRun">
          <el-table-column prop="environment_name" label="环境" min-width="120" />
          <el-table-column prop="path_template" label="路径" min-width="180" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="response_size_bytes" label="消息大小" width="100" />
          <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
        </el-table>
        <el-empty v-else description="尚无 WebSocket 执行记录" />
      </el-card>
    </section>

    <el-card v-if="selectedRun" shadow="never">
      <template #header><h2>接收结果与事件</h2></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="状态">{{ selectedRun.status }}</el-descriptions-item>
        <el-descriptions-item label="响应编码">{{ selectedRun.response_encoding ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="冻结目标" :span="2">
          <code>{{ selectedRun.base_url.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:') }}{{ selectedRun.path_template }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="响应大小">{{ selectedRun.response_size_bytes ?? '—' }} B</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ selectedRun.duration_ms ?? '—' }} ms</el-descriptions-item>
        <el-descriptions-item label="发送 / 接收">
          {{ 1 + selectedRun.additional_message_templates.length }} / {{ selectedRun.receive_count }} 条
        </el-descriptions-item>
        <el-descriptions-item label="连接尝试">{{ selectedRun.attempt_count }} 次</el-descriptions-item>
        <el-descriptions-item label="Ping 心跳">
          {{ selectedRun.ping_interval_seconds === null ? '关闭' : `${selectedRun.ping_interval_seconds} 秒` }}
        </el-descriptions-item>
        <el-descriptions-item label="自动重连">{{ selectedRun.max_reconnect_attempts }} 次</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="selectedRun.error_message"
        :title="`${selectedRun.error_code ?? 'WEBSOCKET_EXECUTION_FAILED'}：${selectedRun.error_message}`"
        type="error"
        :closable="false"
      />
      <h3>有序接收消息</h3>
      <el-table v-if="selectedRun.responses.length" :data="selectedRun.responses">
        <el-table-column prop="ordinal" label="#" width="60" />
        <el-table-column prop="encoding" label="编码" width="90" />
        <el-table-column prop="message" label="消息" min-width="360" />
        <el-table-column prop="size_bytes" label="大小(B)" width="100" />
      </el-table>
      <el-empty v-else description="尚未收到消息" :image-size="72" />
      <h3>消息断言</h3>
      <el-table v-if="selectedRun.assertion_results.length" :data="selectedRun.assertion_results">
        <el-table-column prop="message_index" label="消息索引" width="100" />
        <el-table-column prop="kind" label="类型" min-width="150" />
        <el-table-column prop="path" label="路径" min-width="120" />
        <el-table-column prop="expected" label="期望" min-width="140" />
        <el-table-column prop="actual" label="实际" min-width="140" />
        <el-table-column label="结果" width="100">
          <template #default="scope">{{ scope.row.passed ? '断言通过' : '断言失败' }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="未配置消息断言" :image-size="72" />
      <h3>安全事件</h3>
      <el-table v-if="selectedRun.events.length" :data="selectedRun.events">
        <el-table-column prop="ordinal" label="#" width="60" />
        <el-table-column prop="code" label="事件代码" min-width="210" />
        <el-table-column prop="message" label="说明" min-width="220" />
        <el-table-column prop="created_at" label="时间" min-width="190" />
      </el-table>
      <el-empty v-else description="暂无执行事件" :image-size="72" />
    </el-card>
  </main>
</template>

<style scoped>
.execution-page { display: grid; gap: 20px; max-width: 1180px; margin: 0 auto; padding: 36px clamp(20px, 5vw, 72px) 56px; color: var(--app-text); }
.page-heading, .actions { display: flex; align-items: center; gap: 12px; }
.page-heading { justify-content: space-between; }
.eyebrow { margin: 0 0 6px; color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: .16em; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 8px; }
h2 { margin-bottom: 0; }
.two-column { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
.endpoint-preview { overflow-wrap: anywhere; color: var(--app-muted); }
.field-help { margin: 8px 0 0; color: var(--app-muted); font-size: 12px; }
code, pre { overflow-wrap: anywhere; color: var(--app-text); }
pre { overflow: auto; max-height: 340px; padding: 12px; border: 1px solid var(--app-border); border-radius: 8px; background: var(--app-background); white-space: pre-wrap; }
@media (max-width: 800px) { .two-column { grid-template-columns: 1fr; } }
</style>
