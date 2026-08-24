<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElEmpty,
  ElProgress,
  ElSelect,
  ElOption,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import {
  resolveDroppedDocumentPaths,
  selectDocumentFiles,
} from "../api/backend-connection";
import type { DocumentStatus } from "../api/documents";
import { useDocumentStore } from "../stores/documents";
import { useTaskEventStore } from "../stores/task-events";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const documentStore = useDocumentStore();
const taskEventStore = useTaskEventStore();
const { items: workspaces, activeWorkspace } = storeToRefs(workspaceStore);
const {
  items,
  selected,
  chunks,
  importResults,
  loading,
  importing,
  cancellingJobId,
  loadingChunks,
  error,
} = storeToRefs(documentStore);
const { state: taskEventState, workspaceId: eventWorkspaceId } = storeToRefs(taskEventStore);
const workspaceId = ref("");
const pickerError = ref<string | null>(null);
const dragActive = ref(false);
let dragDepth = 0;
let pollHandle: number | null = null;

const hasActiveJobs = computed(() =>
  items.value.some((item) => ["pending", "queued", "running"].includes(item.job.status)),
);
const realtimeConnected = computed(
  () => taskEventState.value === "connected" && eventWorkspaceId.value === workspaceId.value,
);
const importSummary = computed(() => {
  if (importResults.value.length === 0) return null;
  const accepted = importResults.value.filter((result) => result.status === "accepted").length;
  const rejected = importResults.value.length - accepted;
  return `${accepted} 个文件已加入解析，${rejected} 个文件未导入。`;
});

function statusLabel(status: DocumentStatus): string {
  return {
    pending: "等待中",
    queued: "已排队",
    running: "解析中",
    passed: "已完成",
    failed: "解析失败",
    error: "进程错误",
    cancelled: "已取消",
    timeout: "已超时",
  }[status];
}

function statusType(status: DocumentStatus): "success" | "warning" | "danger" | "info" {
  if (status === "passed") return "success";
  if (["failed", "error", "timeout"].includes(status)) return "danger";
  if (status === "cancelled") return "warning";
  return "info";
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

async function loadWorkspace(): Promise<void> {
  documentStore.clearImportResults();
  if (!workspaceId.value) {
    documentStore.items = [];
    documentStore.selected = null;
    documentStore.clearChunks();
    return;
  }
  await documentStore.refresh(workspaceId.value);
  await loadSelectedChunks();
  schedulePoll();
}

async function loadSelectedChunks(): Promise<void> {
  if (!selected.value || selected.value.job.status !== "passed") {
    documentStore.clearChunks();
    return;
  }
  await documentStore.loadChunks(workspaceId.value, selected.value.id);
}

async function selectDocument(documentId: string): Promise<void> {
  documentStore.selected = items.value.find((item) => item.id === documentId) ?? null;
  await loadSelectedChunks();
}

async function chooseDocuments(): Promise<void> {
  if (!workspaceId.value || importing.value) return;
  pickerError.value = null;
  try {
    const paths = await selectDocumentFiles();
    await importPaths(paths);
  } catch (reason: unknown) {
    if (documentStore.error === null) {
      pickerError.value = reason instanceof Error ? reason.message : "无法选择文档。";
    }
  }
}

async function importPaths(paths: string[]): Promise<void> {
  if (!workspaceId.value || paths.length === 0) return;
  await documentStore.importFiles(workspaceId.value, paths);
  await loadSelectedChunks();
  schedulePoll();
}

function handleDragEnter(): void {
  dragDepth += 1;
  dragActive.value = true;
}

function handleDragLeave(): void {
  dragDepth = Math.max(0, dragDepth - 1);
  dragActive.value = dragDepth > 0;
}

async function handleDrop(event: DragEvent): Promise<void> {
  dragDepth = 0;
  dragActive.value = false;
  if (!workspaceId.value || importing.value) return;
  pickerError.value = null;
  try {
    const files = Array.from(event.dataTransfer?.files ?? []);
    const paths = await resolveDroppedDocumentPaths(files);
    if (paths.length === 0) {
      pickerError.value = "未检测到可读取的本地文件。";
      return;
    }
    await importPaths(paths);
  } catch (reason: unknown) {
    if (documentStore.error === null) {
      pickerError.value = reason instanceof Error ? reason.message : "无法导入拖入的文档。";
    }
  }
}

function fileName(path: string): string {
  return path.split(/[\\/]/).at(-1) ?? path;
}

async function cancelJob(jobId: string): Promise<void> {
  try {
    await documentStore.cancel(jobId);
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

function schedulePoll(): void {
  if (pollHandle !== null) window.clearTimeout(pollHandle);
  if (!workspaceId.value || !hasActiveJobs.value || realtimeConnected.value) return;
  pollHandle = window.setTimeout(async () => {
    await documentStore.refresh(workspaceId.value);
    await loadSelectedChunks();
    schedulePoll();
  }, 750);
}

onMounted(async () => {
  if (workspaces.value.length === 0) await workspaceStore.refresh();
  workspaceId.value = activeWorkspace.value?.id ?? workspaces.value[0]?.id ?? "";
  await loadWorkspace();
});

watch(realtimeConnected, schedulePoll);

onUnmounted(() => {
  if (pollHandle !== null) window.clearTimeout(pollHandle);
});
</script>

<template>
  <main class="documents-page">
    <header class="documents-heading">
      <div>
        <p class="eyebrow">DOCUMENT PIPELINE</p>
        <h1>需求文档</h1>
        <p>支持多选或拖入 Markdown、TXT、DOCX 和 PDF；解析在独立 Worker 进程中执行。</p>
      </div>
      <div class="document-actions">
        <el-select
          v-model="workspaceId"
          aria-label="导入目标工作空间"
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
          data-testid="select-document-file"
          type="primary"
          :disabled="!workspaceId"
          :loading="importing"
          @click="chooseDocuments"
        >
          选择并批量导入
        </el-button>
      </div>
    </header>

    <el-alert
      title="源文件不会上传；PDF 只提取文本层且不执行 OCR；数据库记录相对路径、SHA-256、状态、文本预览和稳定引用片段。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error || pickerError" :title="error ?? pickerError ?? ''" type="error" :closable="false" show-icon />

    <section
      data-testid="document-drop-zone"
      class="document-drop-zone"
      :class="{ active: dragActive, disabled: !workspaceId || importing }"
      role="button"
      :tabindex="workspaceId && !importing ? 0 : -1"
      @click="chooseDocuments"
      @keydown.enter.prevent="chooseDocuments"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <strong>拖入一个或多个需求文档</strong>
      <span>也可点击此处多选；单次最多 50 个文件。</span>
    </section>

    <el-alert
      v-if="importSummary"
      :title="importSummary"
      :type="importResults.some((result) => result.status === 'rejected') ? 'warning' : 'success'"
      :closable="false"
      show-icon
    />
    <ul v-if="importResults.length > 0" class="import-results" aria-label="批量导入结果">
      <li
        v-for="(result, index) in importResults"
        :key="`${index}:${result.source_path}:${result.status}`"
      >
        <span>{{ fileName(result.source_path) }}</span>
        <el-tag :type="result.status === 'accepted' ? 'success' : 'danger'" size="small">
          {{ result.status === "accepted" ? "已加入解析" : (result.error_message ?? "未导入") }}
        </el-tag>
      </li>
    </ul>

    <section class="document-grid" v-loading="loading">
      <el-card shadow="never">
        <template #header><h2>文档与版本</h2></template>
        <el-empty v-if="items.length === 0" description="当前工作空间还没有文档" />
        <div v-else class="document-list">
          <button
            v-for="document in items"
            :key="document.id"
            class="document-item"
            :class="{ selected: selected?.id === document.id }"
            type="button"
            @click="selectDocument(document.id)"
          >
            <span class="document-title">
              <strong>{{ document.name }}</strong>
              <el-tag :type="statusType(document.job.status)" size="small">
                {{ statusLabel(document.job.status) }}
              </el-tag>
            </span>
            <small>版本 {{ document.latest_version.version_number }} · {{ formatBytes(document.latest_version.size_bytes) }}</small>
            <el-progress
              v-if="['pending', 'queued', 'running'].includes(document.job.status)"
              :percentage="document.job.progress"
              :stroke-width="6"
            />
          </button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="preview-title">
            <h2>解析文本预览</h2>
            <el-button
              v-if="selected?.job.status === 'queued' || selected?.job.status === 'running'"
              type="danger"
              plain
              :loading="cancellingJobId === selected.job.id"
              @click="cancelJob(selected.job.id)"
            >
              取消解析
            </el-button>
          </div>
        </template>
        <el-empty v-if="!selected" description="选择一个文档查看详情" />
        <template v-else>
          <dl class="document-metadata">
            <div><dt>相对路径</dt><dd>{{ selected.relative_path }}</dd></div>
            <div><dt>SHA-256</dt><dd><code>{{ selected.latest_version.sha256 }}</code></dd></div>
          </dl>
          <el-alert
            v-if="selected.job.error_message"
            :title="selected.job.error_message"
            type="error"
            :closable="false"
            show-icon
          />
          <div v-if="chunks.length > 0" class="chunk-list" v-loading="loadingChunks">
            <article
              v-for="chunk in chunks"
              :id="`document-chunk-${chunk.id}`"
              :key="chunk.id"
              class="document-chunk"
              :data-chunk-id="chunk.id"
            >
              <header>
                <strong>引用片段 {{ chunk.ordinal }}</strong>
                <el-tag size="small" type="info">{{ chunk.locator }}</el-tag>
              </header>
              <pre>{{ chunk.text }}</pre>
              <small>稳定引用 ID：<code>{{ chunk.id }}</code></small>
            </article>
          </div>
          <pre v-else-if="selected.latest_version.parsed_text !== null">{{ selected.latest_version.parsed_text }}</pre>
          <el-empty v-else description="解析完成后将在这里显示文本" />
        </template>
      </el-card>
    </section>
  </main>
</template>

<style scoped>
.documents-page {
  display: grid;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 36px clamp(20px, 5vw, 72px) 56px;
  color: var(--app-text);
}

.documents-heading,
.document-actions,
.preview-title,
.document-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.document-actions .el-select {
  width: 220px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #409eff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

h1,
h2,
p {
  margin-top: 0;
}

h1,
h2,
.documents-heading p {
  margin-bottom: 0;
}

h2 {
  font-size: 18px;
}

.document-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.75fr) minmax(400px, 1.25fr);
  gap: 20px;
}

.document-list {
  display: grid;
  gap: 10px;
}

.document-drop-zone {
  display: grid;
  gap: 6px;
  padding: 22px;
  border: 2px dashed var(--app-border);
  border-radius: 12px;
  color: var(--app-muted);
  background: var(--app-surface);
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.document-drop-zone strong {
  color: var(--app-text);
}

.document-drop-zone.active {
  border-color: #409eff;
  background: color-mix(in srgb, #409eff 10%, var(--app-surface));
}

.document-drop-zone.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.import-results {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.import-results li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.document-item {
  display: grid;
  gap: 8px;
  width: 100%;
  padding: 14px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  color: var(--app-text);
  background: var(--app-surface);
  text-align: left;
  cursor: pointer;
}

.document-item.selected {
  border-color: #409eff;
}

.document-item small,
dt {
  color: var(--app-muted);
}

.document-metadata {
  display: grid;
  gap: 10px;
}

.document-metadata div {
  display: grid;
  gap: 4px;
}

.document-metadata dd {
  margin: 0;
  overflow-wrap: anywhere;
}

pre {
  max-height: 460px;
  overflow: auto;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  color: var(--app-text);
  background: var(--app-background);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chunk-list {
  display: grid;
  gap: 12px;
  max-height: 520px;
  overflow: auto;
}

.document-chunk {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  scroll-margin-top: 12px;
}

.document-chunk header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.document-chunk pre {
  max-height: none;
  margin: 0;
}

.document-chunk small {
  color: var(--app-muted);
  overflow-wrap: anywhere;
}

@media (max-width: 820px) {
  .documents-heading,
  .document-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .document-actions .el-select,
  .document-grid {
    width: 100%;
  }

  .document-grid {
    grid-template-columns: 1fr;
  }
}
</style>
