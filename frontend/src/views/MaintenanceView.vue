<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElEmpty,
  ElTable,
  ElTableColumn,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { onMounted } from "vue";

import { useMaintenanceStore } from "../stores/maintenance";

const maintenanceStore = useMaintenanceStore();
const { diagnostics, backups, loading, creating, error } = storeToRefs(maintenanceStore);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium" }).format(
    new Date(value),
  );
}

async function createDatabaseBackup(): Promise<void> {
  try {
    await maintenanceStore.create();
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

onMounted(() => void maintenanceStore.refresh());
</script>

<template>
  <main class="maintenance-page" v-loading="loading">
    <header class="maintenance-heading">
      <div>
        <p class="eyebrow">LOCAL MAINTENANCE</p>
        <h1>备份与诊断</h1>
        <p>查看本地运行状态，并为业务数据库创建一致性备份。</p>
      </div>
      <el-button
        data-testid="create-database-backup"
        type="primary"
        :loading="creating"
        @click="createDatabaseBackup"
      >
        创建数据库备份
      </el-button>
    </header>

    <el-alert
      title="备份只包含应用 SQLite 业务数据库，不包含工作空间原文件或系统凭据。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-card class="diagnostics-card" shadow="never">
      <template #header>
        <div class="card-title">
          <h2>本机诊断</h2>
          <el-tag :type="diagnostics?.database_integrity === 'ok' ? 'success' : 'warning'">
            数据库 {{ diagnostics?.database_integrity ?? "未知" }}
          </el-tag>
        </div>
      </template>
      <el-descriptions v-if="diagnostics" :column="2" border>
        <el-descriptions-item label="应用版本">{{ diagnostics.app_version }}</el-descriptions-item>
        <el-descriptions-item label="Python">{{ diagnostics.python_version }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ diagnostics.platform }}</el-descriptions-item>
        <el-descriptions-item label="API 监听">{{ diagnostics.api_host }}</el-descriptions-item>
        <el-descriptions-item label="数据库版本">
          {{ diagnostics.database_revision ?? "未初始化" }}
        </el-descriptions-item>
        <el-descriptions-item label="数据库大小">
          {{ formatBytes(diagnostics.database_size_bytes) }}
        </el-descriptions-item>
        <el-descriptions-item label="工作空间数">{{ diagnostics.workspace_count }}</el-descriptions-item>
        <el-descriptions-item label="备份数">{{ diagnostics.backup_count }}</el-descriptions-item>
        <el-descriptions-item label="数据库路径" :span="2">
          <code>{{ diagnostics.database_path }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="备份目录" :span="2">
          <code>{{ diagnostics.backup_directory }}</code>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never">
      <template #header><h2>数据库备份</h2></template>
      <el-table v-if="backups.length > 0" :data="backups">
        <el-table-column prop="file_name" label="文件" min-width="220" />
        <el-table-column label="创建时间" min-width="180">
          <template #default="scope">{{ formatTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="大小" width="120">
          <template #default="scope">{{ formatBytes(scope.row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column prop="path" label="本地路径" min-width="320" />
      </el-table>
      <el-empty v-else description="尚未创建数据库备份" />
    </el-card>
  </main>
</template>

<style scoped>
.maintenance-page {
  display: grid;
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
  padding: 36px clamp(20px, 5vw, 72px) 56px;
  color: var(--app-text);
}

.maintenance-heading,
.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
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

h1 {
  margin-bottom: 8px;
}

h2,
.maintenance-heading p {
  margin-bottom: 0;
}

code {
  overflow-wrap: anywhere;
  color: var(--app-text);
}

@media (max-width: 680px) {
  .maintenance-heading {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
