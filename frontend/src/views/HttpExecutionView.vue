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
  ElMessageBox,
  ElOption,
  ElProgress,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import type { HttpAssertion, HttpEnvironmentInput, HttpMethod } from "../api/http-execution";
import { useHttpExecutionStore } from "../stores/http-execution";
import { useTaskEventStore } from "../stores/task-events";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const executionStore = useHttpExecutionStore();
const taskEventStore = useTaskEventStore();
const { activeWorkspaceId } = storeToRefs(workspaceStore);
const {
  environments,
  selectedEnvironmentId,
  selectedEnvironment,
  runs,
  selectedRun,
  loading,
  savingEnvironment,
  savingSecret,
  starting,
  cancelling,
  rerunning,
  error,
} = storeToRefs(executionStore);
const { state: taskEventState, workspaceId: eventWorkspaceId } = storeToRefs(taskEventStore);

const environmentEditingId = ref<string | null>(null);
const environmentName = ref("");
const baseUrl = ref("http://127.0.0.1:8000");
const variablesJson = ref("{}");
const secretName = ref("");
const secretValue = ref("");
const method = ref<HttpMethod>("GET");
const path = ref("/health");
const headersJson = ref("{}");
const requestBody = ref("");
const timeoutSeconds = ref(30);
const maxAttempts = ref(1);
const expectedStatus = ref("200");
const expectedHeaderName = ref("");
const expectedHeaderValue = ref("");
const expectedBodyText = ref("");
const expectedJsonPath = ref("");
const expectedJsonValue = ref("");
const localError = ref<string | null>(null);
let pollTimer: number | null = null;

const retryableMethods = new Set<HttpMethod>(["GET", "HEAD", "OPTIONS"]);
const terminalStatuses = new Set(["passed", "failed", "error", "cancelled", "timeout"]);

const activeRun = computed(
  () => selectedRun.value !== null && ["pending", "queued", "running"].includes(selectedRun.value.status),
);
const realtimeConnected = computed(
  () =>
    taskEventState.value === "connected" && eventWorkspaceId.value === activeWorkspaceId.value,
);
const canStart = computed(
  () => activeWorkspaceId.value !== null && selectedEnvironment.value !== null && !starting.value && !activeRun.value,
);
const canRetry = computed(() => retryableMethods.has(method.value));
const canRerun = computed(
  () => selectedRun.value !== null && terminalStatuses.has(selectedRun.value.status),
);
const requestEndpoint = computed(
  () => `${selectedEnvironment.value?.base_url ?? ""}${path.value || "/"}`,
);

function parseStringMap(value: string, label: string): Record<string, string> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label}必须是 JSON 对象。`);
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Object.values(parsed).every((item) => typeof item === "string")
  ) {
    throw new Error(`${label}的键和值都必须是字符串。`);
  }
  return parsed as Record<string, string>;
}

function buildAssertions(): HttpAssertion[] {
  const assertions: HttpAssertion[] = [];
  if (expectedStatus.value.trim()) {
    assertions.push({ kind: "status_code", target: null, expected: expectedStatus.value.trim() });
  }
  if (expectedHeaderName.value.trim() || expectedHeaderValue.value) {
    if (!expectedHeaderName.value.trim() || !expectedHeaderValue.value) {
      throw new Error("响应头断言必须同时填写名称和预期值。");
    }
    assertions.push({
      kind: "header_equals",
      target: expectedHeaderName.value.trim(),
      expected: expectedHeaderValue.value,
    });
  }
  if (expectedBodyText.value) {
    assertions.push({ kind: "body_contains", target: null, expected: expectedBodyText.value });
  }
  if (expectedJsonPath.value.trim() || expectedJsonValue.value) {
    if (!expectedJsonPath.value.trim() || !expectedJsonValue.value) {
      throw new Error("JSON 路径断言必须同时填写路径和 JSON 标量预期值。");
    }
    try {
      const parsed = JSON.parse(expectedJsonValue.value);
      if (typeof parsed === "object" && parsed !== null) throw new Error();
    } catch {
      throw new Error("JSON 路径断言的预期值必须是合法 JSON 标量，例如 42、true 或 \"ok\"。");
    }
    assertions.push({
      kind: "json_path_equals",
      target: expectedJsonPath.value.trim(),
      expected: expectedJsonValue.value,
    });
  }
  return assertions;
}

function resetEnvironmentForm(): void {
  environmentEditingId.value = null;
  environmentName.value = "";
  baseUrl.value = "http://127.0.0.1:8000";
  variablesJson.value = "{}";
  localError.value = null;
}

function editEnvironment(): void {
  if (selectedEnvironment.value === null) return;
  environmentEditingId.value = selectedEnvironment.value.id;
  environmentName.value = selectedEnvironment.value.name;
  baseUrl.value = selectedEnvironment.value.base_url;
  variablesJson.value = JSON.stringify(selectedEnvironment.value.variables, null, 2);
}

async function saveEnvironment(): Promise<void> {
  if (activeWorkspaceId.value === null) return;
  localError.value = null;
  try {
    const input: HttpEnvironmentInput = {
      name: environmentName.value,
      base_url: baseUrl.value,
      variables: parseStringMap(variablesJson.value, "普通变量"),
    };
    await executionStore.saveEnvironment(
      activeWorkspaceId.value,
      input,
      environmentEditingId.value,
    );
    editEnvironment();
  } catch (reason: unknown) {
    localError.value = reason instanceof Error ? reason.message : "HTTP 环境保存失败。";
  }
}

async function removeEnvironment(): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null) return;
  try {
    await ElMessageBox.confirm(
      "删除环境会清除其操作系统凭据库中的全部安全变量；历史执行结果仍保留。",
      "删除 HTTP 环境",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
    await executionStore.removeEnvironment(activeWorkspaceId.value, selectedEnvironment.value.id);
    resetEnvironmentForm();
  } catch {
    // Cancellation and safe store errors need no additional side effect.
  }
}

async function saveSecret(): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null) return;
  localError.value = null;
  try {
    await executionStore.saveSecret(
      activeWorkspaceId.value,
      selectedEnvironment.value.id,
      secretName.value,
      secretValue.value,
    );
    secretName.value = "";
  } catch (reason: unknown) {
    localError.value = reason instanceof Error ? reason.message : "安全变量保存失败。";
  } finally {
    secretValue.value = "";
  }
}

async function removeSecret(name: string): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null) return;
  try {
    await executionStore.removeSecret(activeWorkspaceId.value, selectedEnvironment.value.id, name);
  } catch {
    // Store error remains visible and recoverable.
  }
}

async function startExecution(): Promise<void> {
  if (activeWorkspaceId.value === null || selectedEnvironment.value === null) return;
  localError.value = null;
  try {
    await executionStore.start(activeWorkspaceId.value, {
      environment_id: selectedEnvironment.value.id,
      method: method.value,
      path: path.value,
      headers: parseStringMap(headersJson.value, "请求头"),
      body: requestBody.value === "" ? null : requestBody.value,
      timeout_seconds: timeoutSeconds.value,
      max_attempts: canRetry.value ? maxAttempts.value : 1,
      assertions: buildAssertions(),
    });
    schedulePoll();
  } catch (reason: unknown) {
    localError.value = reason instanceof Error ? reason.message : "HTTP 请求启动失败。";
  }
}

async function rerunExecution(): Promise<void> {
  if (activeWorkspaceId.value === null || !canRerun.value) return;
  localError.value = null;
  try {
    await executionStore.rerun(activeWorkspaceId.value);
    schedulePoll();
  } catch (reason: unknown) {
    localError.value = reason instanceof Error ? reason.message : "HTTP 请求重跑失败。";
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
    resetEnvironmentForm();
    if (workspaceId !== null) await executionStore.refresh(workspaceId);
    schedulePoll();
  },
  { immediate: true },
);

watch(selectedEnvironmentId, () => editEnvironment());
watch(method, (nextMethod) => {
  if (!retryableMethods.has(nextMethod)) maxAttempts.value = 1;
});
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
        <p class="eyebrow">M5 · HTTP RUNNER</p>
        <h1>HTTP 接口执行</h1>
        <p>配置环境、断言和安全重试策略，在独立 Worker 中执行并保留可审计事件。</p>
      </div>
      <el-button :disabled="activeWorkspaceId === null" @click="resetEnvironmentForm">
        新建环境
      </el-button>
    </header>

    <el-alert
      v-if="activeWorkspaceId === null"
      title="请先在工作空间页面打开一个工作空间。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      title="安全变量值只写入操作系统凭据库。请求执行会连接所选环境地址，且不会自动跟随重定向。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert v-if="localError || error" :title="localError ?? error ?? ''" type="error" :closable="false" />

    <section class="two-column">
      <el-card shadow="never">
        <template #header><h2>环境与变量</h2></template>
        <el-form label-position="top">
          <el-form-item label="已保存环境">
            <el-select v-model="selectedEnvironmentId" placeholder="请选择环境" style="width: 100%">
              <el-option v-for="item in environments" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="环境名称"><el-input v-model="environmentName" maxlength="120" /></el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="baseUrl" placeholder="https://api.example.com/v1" />
          </el-form-item>
          <el-form-item label="普通变量（JSON 字符串对象）">
            <el-input v-model="variablesJson" type="textarea" :rows="4" />
          </el-form-item>
          <div class="actions">
            <el-button
              data-testid="save-http-environment"
              type="primary"
              :loading="savingEnvironment"
              :disabled="activeWorkspaceId === null"
              @click="saveEnvironment"
            >保存环境</el-button>
            <el-button v-if="selectedEnvironment" type="danger" plain @click="removeEnvironment">删除</el-button>
          </div>
        </el-form>

        <div class="secret-section">
          <h3>安全变量</h3>
          <p>请求模板使用 <code v-pre>{{secret.API_TOKEN}}</code> 引用；值不会回显。</p>
          <div class="secret-inputs">
            <el-input v-model="secretName" placeholder="API_TOKEN" />
            <el-input
              v-model="secretValue"
              data-testid="http-secret-value"
              type="password"
              show-password
              placeholder="安全变量值"
            />
            <el-button
              data-testid="save-http-secret"
              :loading="savingSecret"
              :disabled="selectedEnvironment === null"
              @click="saveSecret"
            >保存</el-button>
          </div>
          <div class="tag-list">
            <el-tag v-for="name in selectedEnvironment?.secret_names ?? []" :key="name" closable @close="removeSecret(name)">
              {{ name }} · 已配置
            </el-tag>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header><h2>单次请求</h2></template>
        <el-form label-position="top">
          <div class="request-line">
            <el-select v-model="method" style="width: 130px">
              <el-option v-for="item in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']" :key="item" :label="item" :value="item" />
            </el-select>
            <el-input v-model="path" placeholder="/health" />
          </div>
          <p class="endpoint-preview">目标：<code>{{ requestEndpoint }}</code></p>
          <el-form-item label="请求头（JSON 字符串对象）">
            <el-input v-model="headersJson" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="请求体（UTF-8，可使用变量引用）">
            <el-input v-model="requestBody" type="textarea" :rows="7" />
          </el-form-item>
          <el-form-item label="请求超时（秒）">
            <el-input-number v-model="timeoutSeconds" :min="1" :max="60" />
          </el-form-item>
          <el-form-item label="最大尝试次数">
            <el-input-number
              v-model="maxAttempts"
              data-testid="http-max-attempts"
              :min="1"
              :max="3"
              :disabled="!canRetry"
            />
            <p class="form-hint">
              仅 GET、HEAD、OPTIONS 可在超时或服务不可用时重试，其他方法固定为 1 次。
            </p>
          </el-form-item>
          <div class="assertion-section">
            <h3>响应断言</h3>
            <p class="form-hint">留空即不启用该项；全部断言通过时任务才会标记 passed。</p>
            <el-form-item label="预期 HTTP 状态码">
              <el-input v-model="expectedStatus" data-testid="http-expected-status" placeholder="200" />
            </el-form-item>
            <div class="assertion-pair">
              <el-form-item label="响应头名称">
                <el-input v-model="expectedHeaderName" placeholder="Content-Type" />
              </el-form-item>
              <el-form-item label="响应头预期值">
                <el-input v-model="expectedHeaderValue" placeholder="application/json" />
              </el-form-item>
            </div>
            <el-form-item label="响应正文包含">
              <el-input v-model="expectedBodyText" placeholder="success" />
            </el-form-item>
            <div class="assertion-pair">
              <el-form-item label="JSON 路径（点号语法）">
                <el-input v-model="expectedJsonPath" placeholder="$.data.items.0.id" />
              </el-form-item>
              <el-form-item label="JSON 标量预期值">
                <el-input v-model="expectedJsonValue" placeholder="42 或 &quot;ok&quot;" />
              </el-form-item>
            </div>
          </div>
          <div class="actions">
            <el-button
              data-testid="start-http-execution"
              type="primary"
              :loading="starting"
              :disabled="!canStart"
              @click="startExecution"
            >运行请求</el-button>
            <el-button v-if="activeRun" :loading="cancelling" @click="cancelExecution">取消任务</el-button>
          </div>
        </el-form>
      </el-card>
    </section>

    <el-card shadow="never">
      <template #header><h2>执行历史与结果</h2></template>
      <el-progress v-if="selectedRun && activeRun" :percentage="selectedRun.progress" />
      <el-table v-if="runs.length" :data="runs" highlight-current-row @current-change="selectRun">
        <el-table-column prop="method" label="方法" width="90" />
        <el-table-column prop="environment_name" label="环境" min-width="130" />
        <el-table-column prop="path_template" label="路径模板" min-width="220" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="response_status_code" label="HTTP" width="90" />
        <el-table-column prop="duration_ms" label="耗时(ms)" width="110" />
      </el-table>
      <el-empty v-else description="尚无 HTTP 执行记录" />

      <div v-if="selectedRun" class="result-panel">
        <div class="result-heading">
          <h3>运行详情</h3>
          <el-button
            v-if="canRerun"
            data-testid="rerun-http-execution"
            :loading="rerunning"
            :disabled="activeRun"
            @click="rerunExecution"
          >按冻结模板重跑</el-button>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="状态">{{ selectedRun.status }}</el-descriptions-item>
          <el-descriptions-item label="HTTP 状态码">{{ selectedRun.response_status_code ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="冻结目标" :span="2">
            <code>{{ selectedRun.base_url }}{{ selectedRun.path_template }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="响应大小">{{ selectedRun.response_size_bytes ?? '—' }} B</el-descriptions-item>
          <el-descriptions-item label="响应编码">{{ selectedRun.response_body_encoding ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="最大尝试次数">{{ selectedRun.max_attempts }}</el-descriptions-item>
          <el-descriptions-item label="断言数量">{{ selectedRun.assertions.length }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="selectedRun.error_message"
          :title="`${selectedRun.error_code ?? 'HTTP_EXECUTION_FAILED'}：${selectedRun.error_message}`"
          type="error"
          :closable="false"
        />
        <h3>响应头（敏感字段已脱敏）</h3>
        <pre>{{ JSON.stringify(selectedRun.response_headers, null, 2) }}</pre>
        <h3>响应体{{ selectedRun.response_body_encoding === 'base64' ? '（Base64）' : '' }}</h3>
        <pre>{{ selectedRun.response_body ?? '—' }}</pre>
        <h3>断言结果</h3>
        <el-table v-if="selectedRun.assertion_results.length" :data="selectedRun.assertion_results">
          <el-table-column label="结果" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.passed ? 'success' : 'danger'">
                {{ scope.row.passed ? '通过' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="kind" label="类型" width="150" />
          <el-table-column prop="target" label="目标" min-width="150" />
          <el-table-column prop="expected" label="预期" min-width="120" />
          <el-table-column prop="actual" label="实际" min-width="120" />
          <el-table-column prop="message" label="说明" min-width="210" />
        </el-table>
        <el-empty v-else description="该运行未配置断言或尚未产生断言结果" :image-size="72" />
        <h3>执行事件</h3>
        <el-table v-if="selectedRun.events.length" :data="selectedRun.events">
          <el-table-column prop="ordinal" label="#" width="60" />
          <el-table-column prop="attempt" label="尝试" width="75" />
          <el-table-column prop="code" label="事件代码" min-width="190" />
          <el-table-column prop="message" label="说明" min-width="220" />
          <el-table-column prop="created_at" label="时间" min-width="190" />
        </el-table>
        <el-empty v-else description="暂无执行事件" :image-size="72" />
      </div>
    </el-card>
  </main>
</template>

<style scoped>
.execution-page { display: grid; gap: 20px; max-width: 1180px; margin: 0 auto; padding: 36px clamp(20px, 5vw, 72px) 56px; color: var(--app-text); }
.page-heading, .actions, .request-line, .secret-inputs { display: flex; align-items: center; gap: 12px; }
.page-heading { justify-content: space-between; }
.eyebrow { margin: 0 0 6px; color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: .16em; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 8px; }
h2 { margin-bottom: 0; }
.two-column { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 20px; }
.secret-section, .result-panel, .assertion-section { margin-top: 24px; }
.secret-inputs { align-items: stretch; }
.assertion-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.assertion-pair .el-form-item { min-width: 0; }
.form-hint { margin: 6px 0 0; color: var(--app-muted); font-size: 13px; }
.result-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.request-line .el-input { flex: 1; }
.endpoint-preview { overflow-wrap: anywhere; color: var(--app-muted); }
code, pre { overflow-wrap: anywhere; color: var(--app-text); }
pre { overflow: auto; max-height: 340px; padding: 12px; border: 1px solid var(--app-border); border-radius: 8px; background: var(--app-background); white-space: pre-wrap; }
@media (max-width: 800px) { .two-column, .assertion-pair { grid-template-columns: 1fr; } .page-heading, .secret-inputs { align-items: stretch; flex-direction: column; } }
</style>
