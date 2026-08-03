<script setup lang="ts">
import { ElAlert, ElButton, ElCard, ElResult, ElTag } from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted } from "vue";

import { useHealthStore } from "../stores/health";

const healthStore = useHealthStore();
const { status, version, error } = storeToRefs(healthStore);

const isLoading = computed(() => status.value === "loading");
const statusType = computed(() => (status.value === "online" ? "success" : "danger"));
const statusText = computed(() =>
  status.value === "online" ? "后端服务正常" : "后端服务离线",
);

onMounted(() => healthStore.refresh());
</script>

<template>
  <main class="health-page">
    <section class="hero" aria-labelledby="page-title">
      <p class="eyebrow">LOCAL-FIRST QA WORKSPACE</p>
      <h1 id="page-title">AI QA Assistant</h1>
      <p class="subtitle">本地服务诊断</p>
    </section>

    <el-card class="health-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>系统状态</span>
          <el-tag v-if="status !== 'idle' && status !== 'loading'" :type="statusType" round>
            {{ statusText }}
          </el-tag>
        </div>
      </template>

      <div class="health-content" aria-live="polite" :aria-busy="isLoading">
        <template v-if="status === 'online'">
          <el-result icon="success" title="后端服务正常" sub-title="本地 API 已安全连接">
            <template #extra>
              <p class="version">后端版本：{{ version }}</p>
            </template>
          </el-result>
        </template>

        <template v-else-if="status === 'offline'">
          <el-alert
            :title="error ?? '无法连接本地后端。'"
            type="error"
            :closable="false"
            show-icon
          />
          <el-button type="primary" :loading="isLoading" @click="healthStore.refresh">
            重新检查
          </el-button>
        </template>

        <p v-else class="checking">正在检查本地后端状态…</p>
      </div>
    </el-card>

    <p class="privacy-note">所有服务默认仅连接本机 127.0.0.1</p>
  </main>
</template>

<style scoped>
.health-page {
  min-height: 100vh;
  box-sizing: border-box;
  display: grid;
  place-content: center;
  gap: 24px;
  padding: 48px 24px;
  color: #172033;
  background:
    radial-gradient(circle at 15% 20%, rgb(64 158 255 / 16%), transparent 32%),
    linear-gradient(145deg, #f7faff 0%, #eef4fb 100%);
}

.hero {
  text-align: center;
}

.eyebrow {
  margin: 0 0 8px;
  color: #337ecc;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

h1 {
  margin: 0;
  font-size: clamp(32px, 6vw, 52px);
  letter-spacing: -0.04em;
}

.subtitle {
  margin: 8px 0 0;
  color: #64748b;
}

.health-card {
  width: min(560px, calc(100vw - 48px));
  border: 1px solid rgb(51 126 204 / 18%);
  border-radius: 18px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 650;
}

.health-content {
  min-height: 220px;
  display: grid;
  place-items: center;
  gap: 24px;
}

.version,
.checking,
.privacy-note {
  color: #64748b;
}

.version {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.privacy-note {
  margin: 0;
  text-align: center;
  font-size: 13px;
}
</style>
