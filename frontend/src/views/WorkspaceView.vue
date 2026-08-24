<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted, reactive, ref } from "vue";

import { selectWorkspaceDirectory } from "../api/backend-connection";
import { useHealthStore } from "../stores/health";
import { useWorkspaceStore } from "../stores/workspaces";

const healthStore = useHealthStore();
const workspaceStore = useWorkspaceStore();
const { status, version } = storeToRefs(healthStore);
const { items, activeWorkspace, loading, creating, openingId, renamingId, deletingId, error } =
  storeToRefs(workspaceStore);

const form = reactive({ name: "", path: "" });
const selectingDirectory = ref(false);
const directoryError = ref<string | null>(null);
const editingId = ref<string | null>(null);
const renameName = ref("");
const confirmingDeleteId = ref<string | null>(null);
const canCreate = computed(() => form.name.trim().length > 0 && form.path.trim().length > 0);

function formatLastOpened(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function submitWorkspace(): Promise<void> {
  if (!canCreate.value) {
    return;
  }
  try {
    await workspaceStore.create(form.name, form.path);
    form.name = "";
    form.path = "";
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

async function chooseWorkspaceDirectory(): Promise<void> {
  selectingDirectory.value = true;
  directoryError.value = null;
  try {
    const selectedPath = await selectWorkspaceDirectory();
    if (selectedPath !== null) {
      form.path = selectedPath;
    }
  } catch (reason: unknown) {
    directoryError.value = reason instanceof Error ? reason.message : "无法选择工作空间目录。";
  } finally {
    selectingDirectory.value = false;
  }
}

async function selectWorkspace(workspaceId: string): Promise<void> {
  try {
    await workspaceStore.open(workspaceId);
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

function beginRename(workspaceId: string, currentName: string): void {
  confirmingDeleteId.value = null;
  editingId.value = workspaceId;
  renameName.value = currentName;
}

function cancelRename(): void {
  editingId.value = null;
  renameName.value = "";
}

async function saveRename(workspaceId: string): Promise<void> {
  if (!renameName.value.trim()) {
    return;
  }
  try {
    await workspaceStore.rename(workspaceId, renameName.value);
    cancelRename();
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

function beginDelete(workspaceId: string): void {
  cancelRename();
  confirmingDeleteId.value = workspaceId;
}

async function confirmDelete(workspaceId: string): Promise<void> {
  try {
    await workspaceStore.remove(workspaceId);
    confirmingDeleteId.value = null;
  } catch {
    // Keep the confirmation open and expose the safe API message from the store.
  }
}

onMounted(() => {
  void healthStore.refresh();
  void workspaceStore.refresh();
});
</script>

<template>
  <main class="workspace-page">
    <header class="app-header">
      <div>
        <p class="eyebrow">LOCAL-FIRST QA WORKSPACE</p>
        <h1>AI QA Assistant</h1>
      </div>
      <el-tag :type="status === 'online' ? 'success' : 'info'" round>
        {{ status === "online" ? `本地后端 ${version}` : "正在连接本地后端" }}
      </el-tag>
    </header>

    <el-alert
      v-if="activeWorkspace"
      :title="`当前工作空间：${activeWorkspace.name}`"
      :description="activeWorkspace.path"
      type="success"
      :closable="false"
      show-icon
    />

    <section class="workspace-grid" aria-label="工作空间管理">
      <el-card class="create-card" shadow="never">
        <template #header>
          <div>
            <h2>创建工作空间</h2>
            <p>选择本机绝对路径，项目资料默认只保存在该目录。</p>
          </div>
        </template>

        <el-form label-position="top" @submit.prevent="submitWorkspace">
          <el-form-item label="名称">
            <el-input v-model="form.name" maxlength="80" placeholder="例如：支付服务回归" />
          </el-form-item>
          <el-form-item label="本地路径">
            <el-input
              v-model="form.path"
              maxlength="1024"
              placeholder="例如：C:\\QA\\payment"
            >
              <template #append>
                <el-button
                  data-testid="select-workspace-directory"
                  :loading="selectingDirectory"
                  @click="chooseWorkspaceDirectory"
                >
                  浏览…
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-alert
            v-if="directoryError"
            class="directory-error"
            :title="directoryError"
            type="error"
            :closable="false"
            show-icon
          />
          <el-button
            data-testid="create-workspace"
            type="primary"
            :disabled="!canCreate"
            :loading="creating"
            @click="submitWorkspace"
          >
            创建并打开
          </el-button>
        </el-form>
      </el-card>

      <el-card class="recent-card" shadow="never">
        <template #header>
          <div class="recent-header">
            <div>
              <h2>最近工作空间</h2>
              <p>打开后会自动更新最近访问时间。</p>
            </div>
            <el-button text :loading="loading" @click="workspaceStore.refresh">
              重新加载
            </el-button>
          </div>
        </template>

        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
        <el-empty v-else-if="!loading && items.length === 0" description="还没有工作空间" />
        <div v-else class="workspace-list" aria-live="polite">
          <article v-for="workspace in items" :key="workspace.id" class="workspace-item">
            <div class="workspace-summary">
              <template v-if="editingId === workspace.id">
                <el-input
                  v-model="renameName"
                  :data-testid="`rename-input-${workspace.id}`"
                  maxlength="80"
                  aria-label="新的工作空间名称"
                  @keyup.enter="saveRename(workspace.id)"
                  @keyup.esc="cancelRename"
                />
              </template>
              <strong v-else>{{ workspace.name }}</strong>
              <span class="workspace-path">{{ workspace.path }}</span>
              <small>最近打开：{{ formatLastOpened(workspace.last_opened_at) }}</small>
            </div>
            <div class="workspace-actions">
              <template v-if="editingId === workspace.id">
                <el-button
                  :data-testid="`save-rename-${workspace.id}`"
                  type="primary"
                  :loading="renamingId === workspace.id"
                  :disabled="!renameName.trim()"
                  @click="saveRename(workspace.id)"
                >
                  保存
                </el-button>
                <el-button :disabled="renamingId === workspace.id" @click="cancelRename">
                  取消
                </el-button>
              </template>
              <template v-else-if="confirmingDeleteId === workspace.id">
                <p class="delete-warning" role="alert">
                  只删除助手中的记录，不会删除本地目录或文件。
                </p>
                <el-button
                  :data-testid="`confirm-delete-${workspace.id}`"
                  type="danger"
                  :loading="deletingId === workspace.id"
                  @click="confirmDelete(workspace.id)"
                >
                  确认删除记录
                </el-button>
                <el-button
                  :disabled="deletingId === workspace.id"
                  @click="confirmingDeleteId = null"
                >
                  取消
                </el-button>
              </template>
              <template v-else>
                <el-button
                  :loading="openingId === workspace.id"
                  :disabled="openingId !== null && openingId !== workspace.id"
                  @click="selectWorkspace(workspace.id)"
                >
                  打开
                </el-button>
                <el-button
                  :data-testid="`rename-workspace-${workspace.id}`"
                  @click="beginRename(workspace.id, workspace.name)"
                >
                  重命名
                </el-button>
                <el-button
                  :data-testid="`delete-workspace-${workspace.id}`"
                  type="danger"
                  plain
                  @click="beginDelete(workspace.id)"
                >
                  删除记录
                </el-button>
              </template>
            </div>
          </article>
        </div>
      </el-card>
    </section>

    <p class="privacy-note">本地 API 仅监听 127.0.0.1；工作空间路径不会自动上传。</p>
  </main>
</template>

<style scoped>
.workspace-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 40px clamp(20px, 5vw, 72px);
  color: var(--app-text);
  background:
    radial-gradient(circle at 12% 10%, rgb(64 158 255 / 14%), transparent 28%),
    linear-gradient(145deg, var(--app-surface) 0%, var(--app-background) 100%);
}

.app-header,
.recent-header,
.workspace-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.app-header {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #337ecc;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  font-size: clamp(30px, 5vw, 48px);
  letter-spacing: -0.04em;
}

h2 {
  margin-bottom: 6px;
  font-size: 18px;
}

.create-card p,
.recent-card p,
.privacy-note,
.workspace-path,
small {
  color: var(--app-muted);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(360px, 1.2fr);
  gap: 24px;
  margin-top: 24px;
}

.create-card,
.recent-card {
  border: 1px solid rgb(51 126 204 / 18%);
  border-radius: 18px;
}

.workspace-list {
  display: grid;
  gap: 12px;
}

.directory-error {
  margin-bottom: 18px;
}

.workspace-item {
  padding: 16px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
}

.workspace-summary {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.workspace-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.workspace-actions .el-button + .el-button {
  margin-left: 0;
}

.delete-warning {
  flex-basis: 100%;
  margin: 0;
  color: #c45656;
  font-size: 13px;
  text-align: right;
}

.workspace-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.privacy-note {
  margin: 24px 0 0;
  text-align: center;
  font-size: 13px;
}

@media (max-width: 820px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .app-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .workspace-item {
    align-items: stretch;
    flex-direction: column;
  }

  .workspace-actions {
    justify-content: flex-start;
  }

  .delete-warning {
    text-align: left;
  }
}
</style>
