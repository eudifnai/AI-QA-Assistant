<script setup lang="ts">
import { ElButton, ElTag } from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useSettingsStore } from "./stores/settings";
import { useTaskEventStore } from "./stores/task-events";
import { useWorkspaceStore } from "./stores/workspaces";
import AnalysisView from "./views/AnalysisView.vue";
import HttpExecutionView from "./views/HttpExecutionView.vue";
import MaintenanceView from "./views/MaintenanceView.vue";
import ProtoAssetsView from "./views/ProtoAssetsView.vue";
import ProtobufExecutionView from "./views/ProtobufExecutionView.vue";
import ReportsView from "./views/ReportsView.vue";
import DocumentsView from "./views/DocumentsView.vue";
import SettingsView from "./views/SettingsView.vue";
import WorkspaceView from "./views/WorkspaceView.vue";
import WebSocketExecutionView from "./views/WebSocketExecutionView.vue";

const page = ref<
  | "workspaces"
  | "documents"
  | "analysis"
  | "execution"
  | "websocket"
  | "protobuf"
  | "protobuf-execution"
  | "reports"
  | "maintenance"
  | "settings"
>("workspaces");
const settingsStore = useSettingsStore();
const workspaceStore = useWorkspaceStore();
const taskEventStore = useTaskEventStore();
const { activeWorkspaceId } = storeToRefs(workspaceStore);
const { state: taskEventState } = storeToRefs(taskEventStore);
const taskEventStatus = computed(() => {
  if (taskEventState.value === "connected") return { label: "任务实时已连接", type: "success" as const };
  if (taskEventState.value === "reconnecting") return { label: "任务流重连中·轮询兜底", type: "warning" as const };
  if (taskEventState.value === "connecting") return { label: "任务实时连接中", type: "info" as const };
  return { label: "任务实时未连接", type: "info" as const };
});

onMounted(() => {
  void settingsStore.load();
});
watch(
  activeWorkspaceId,
  (workspaceId) => {
    if (workspaceId === null) taskEventStore.stop();
    else taskEventStore.start(workspaceId);
  },
  { immediate: true },
);
onBeforeUnmount(() => taskEventStore.stop());
</script>

<template>
  <div class="app-shell">
    <nav class="app-nav" aria-label="主导航">
      <el-tag
        data-testid="task-event-status"
        :type="taskEventStatus.type"
        effect="plain"
      >{{ taskEventStatus.label }}</el-tag>
      <el-button
        data-testid="open-workspaces"
        :type="page === 'workspaces' ? 'primary' : 'default'"
        @click="page = 'workspaces'"
      >
        工作空间
      </el-button>
      <el-button
        data-testid="open-reports"
        :type="page === 'reports' ? 'primary' : 'default'"
        @click="page = 'reports'"
      >
        报告
      </el-button>
      <el-button
        data-testid="open-analysis"
        :type="page === 'analysis' ? 'primary' : 'default'"
        @click="page = 'analysis'"
      >
        分析
      </el-button>
      <el-button
        data-testid="open-documents"
        :type="page === 'documents' ? 'primary' : 'default'"
        @click="page = 'documents'"
      >
        文档
      </el-button>
      <el-button
        data-testid="open-http-execution"
        :type="page === 'execution' ? 'primary' : 'default'"
        @click="page = 'execution'"
      >
        执行
      </el-button>
      <el-button
        data-testid="open-websocket-execution"
        :type="page === 'websocket' ? 'primary' : 'default'"
        @click="page = 'websocket'"
      >
        WebSocket
      </el-button>
      <el-button
        data-testid="open-proto-assets"
        :type="page === 'protobuf' ? 'primary' : 'default'"
        @click="page = 'protobuf'"
      >
        Protobuf
      </el-button>
      <el-button
        data-testid="open-protobuf-execution"
        :type="page === 'protobuf-execution' ? 'primary' : 'default'"
        @click="page = 'protobuf-execution'"
      >
        Proto 执行
      </el-button>
      <el-button
        data-testid="open-maintenance"
        :type="page === 'maintenance' ? 'primary' : 'default'"
        @click="page = 'maintenance'"
      >
        维护
      </el-button>
      <el-button
        data-testid="open-settings"
        :type="page === 'settings' ? 'primary' : 'default'"
        @click="page = 'settings'"
      >
        设置
      </el-button>
    </nav>
    <WorkspaceView v-if="page === 'workspaces'" />
    <DocumentsView v-else-if="page === 'documents'" />
    <AnalysisView v-else-if="page === 'analysis'" />
    <HttpExecutionView v-else-if="page === 'execution'" />
    <WebSocketExecutionView v-else-if="page === 'websocket'" />
    <ProtoAssetsView v-else-if="page === 'protobuf'" />
    <ProtobufExecutionView v-else-if="page === 'protobuf-execution'" />
    <ReportsView v-else-if="page === 'reports'" />
    <MaintenanceView v-else-if="page === 'maintenance'" />
    <SettingsView v-else />
  </div>
</template>

<style scoped>
.app-nav {
  position: sticky;
  z-index: 10;
  top: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px clamp(20px, 5vw, 72px);
  border-bottom: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-background) 92%, transparent);
  backdrop-filter: blur(12px);
}

.app-nav .el-button + .el-button {
  margin-left: 0;
}

@media (max-width: 900px) {
  .app-nav {
    justify-content: flex-start;
    padding: 8px 12px;
  }
}
</style>
