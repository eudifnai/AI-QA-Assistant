<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElEmpty,
  ElProgress,
  ElStatistic,
  ElTable,
  ElTableColumn,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, watch } from "vue";

import type { FailureCategory, ReportFormat } from "../api/reports";
import { useReportStore } from "../stores/reports";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const reportStore = useReportStore();
const { activeWorkspaceId } = storeToRefs(workspaceStore);
const { snapshot, loading, exporting, error, lastExportPath } = storeToRefs(reportStore);

const passRate = computed(() => snapshot.value?.execution_summary.pass_rate ?? 0);

function formatDuration(value: number | null): string {
  if (value === null) return "-";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value));
}

function typeLabel(value: string): string {
  return { http: "HTTP", websocket: "WebSocket", protobuf: "Protobuf" }[value] ?? value;
}

function statusTag(value: string): "success" | "warning" | "danger" | "info" {
  if (value === "passed") return "success";
  if (value === "failed" || value === "error" || value === "timeout") return "danger";
  if (value === "running" || value === "queued" || value === "pending") return "warning";
  return "info";
}

function categoryLabel(value: FailureCategory): string {
  return {
    product: "产品",
    environment: "环境",
    data: "数据",
    script: "脚本",
    unknown: "未知",
  }[value];
}

function categoryTag(value: FailureCategory): "success" | "warning" | "danger" | "info" {
  if (value === "product") return "danger";
  if (value === "environment" || value === "script") return "warning";
  if (value === "data") return "info";
  return "info";
}

async function exportArtifact(format: ReportFormat): Promise<void> {
  if (activeWorkspaceId.value === null) return;
  try {
    await reportStore.exportReport(activeWorkspaceId.value, format);
  } catch {
    // The store exposes the safe, recoverable export error.
  }
}

function refresh(): void {
  if (activeWorkspaceId.value !== null) void reportStore.refresh(activeWorkspaceId.value);
}

watch(
  activeWorkspaceId,
  (workspaceId) => {
    reportStore.clear();
    if (workspaceId !== null) void reportStore.refresh(workspaceId);
  },
  { immediate: true },
);
</script>

<template>
  <main class="reports-page" v-loading="loading">
    <header class="reports-heading">
      <div>
        <p class="eyebrow">M6 REPORTING</p>
        <h1>质量报告</h1>
        <p v-if="snapshot">{{ snapshot.workspace_name }} · 截至 {{ formatTime(snapshot.generated_at) }}</p>
        <p v-else>聚合当前工作空间的分析、测试设计和接口执行结果。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="activeWorkspaceId === null" @click="refresh">刷新</el-button>
        <el-button data-testid="export-json-report" :loading="exporting" :disabled="!snapshot" @click="exportArtifact('json')">导出 JSON</el-button>
        <el-button data-testid="export-markdown-report" :loading="exporting" :disabled="!snapshot" @click="exportArtifact('markdown')">导出 Markdown</el-button>
        <el-button data-testid="export-html-report" type="primary" :loading="exporting" :disabled="!snapshot" @click="exportArtifact('html')">导出 HTML</el-button>
      </div>
    </header>

    <el-alert
      title="报告不会导出请求/响应正文、凭据值或普通变量值；仅包含冻结目标摘要、统计、稳定失败原因和已脱敏安全事件。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="lastExportPath" :title="`报告已保存到 ${lastExportPath}`" type="success" :closable="false" show-icon />
    <el-empty v-if="activeWorkspaceId === null" description="请先打开一个工作空间" />

    <template v-else-if="snapshot">
      <section class="summary-grid">
        <el-card shadow="never"><el-statistic title="执行总数" :value="snapshot.execution_summary.total" /></el-card>
        <el-card shadow="never"><el-statistic title="通过" :value="snapshot.execution_summary.passed" /></el-card>
        <el-card shadow="never"><el-statistic title="失败/错误" :value="snapshot.execution_summary.failed + snapshot.execution_summary.error" /></el-card>
        <el-card shadow="never"><el-statistic title="取消/超时" :value="snapshot.execution_summary.cancelled + snapshot.execution_summary.timeout" /></el-card>
      </section>

      <el-card shadow="never">
        <template #header><div class="card-title"><h2>通过率与质量设计</h2><el-tag>平均时长 {{ formatDuration(snapshot.execution_summary.average_duration_ms) }}</el-tag></div></template>
        <el-progress :percentage="passRate" :status="passRate >= 80 ? 'success' : undefined" />
        <p class="metric-note">
          通过率按 {{ snapshot.execution_summary.evaluated }} 条有效终态计算，不含取消和进行中任务。
        </p>
        <div class="design-summary">
          <span>最新分析评分 {{ snapshot.analysis_summary.latest_overall_score ?? "-" }}</span>
          <span>分析问题 {{ snapshot.analysis_summary.issue_count }}</span>
          <span>测试点 {{ snapshot.design_summary.test_point_confirmed }}/{{ snapshot.design_summary.test_point_total }} 已确认</span>
          <span>测试用例 {{ snapshot.design_summary.test_case_confirmed }}/{{ snapshot.design_summary.test_case_total }} 已确认</span>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">
            <h2>最近 14 日趋势</h2>
            <el-tag effect="plain">UTC 自然日</el-tag>
          </div>
        </template>
        <el-table :data="snapshot.trend" size="small">
          <el-table-column prop="date" label="日期" min-width="120" />
          <el-table-column prop="evaluated" label="有效终态" width="100" />
          <el-table-column prop="passed" label="通过" width="80" />
          <el-table-column prop="failed" label="失败" width="80" />
          <el-table-column prop="error" label="错误" width="80" />
          <el-table-column prop="cancelled" label="取消" width="80" />
          <el-table-column prop="timeout" label="超时" width="80" />
          <el-table-column label="通过率" width="100">
            <template #default="scope">{{ scope.row.pass_rate.toFixed(2) }}%</template>
          </el-table-column>
          <el-table-column label="平均时长" width="120">
            <template #default="scope">{{ formatDuration(scope.row.average_duration_ms) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">
            <h2>失败归因</h2>
            <el-tag effect="plain">{{ snapshot.failure_attribution_summary.total }} 条</el-tag>
          </div>
        </template>
        <el-alert
          title="本地确定性初步归因：不调用模型，仅依据稳定状态与错误码；未知项需要人工复核。"
          type="warning"
          :closable="false"
          show-icon
        />
        <div class="attribution-summary">
          <span>产品 {{ snapshot.failure_attribution_summary.product }}</span>
          <span>环境 {{ snapshot.failure_attribution_summary.environment }}</span>
          <span>数据 {{ snapshot.failure_attribution_summary.data }}</span>
          <span>脚本 {{ snapshot.failure_attribution_summary.script }}</span>
          <span>未知 {{ snapshot.failure_attribution_summary.unknown }}</span>
        </div>
        <el-table v-if="snapshot.failure_attributions.length" :data="snapshot.failure_attributions">
          <el-table-column label="类型" width="110"><template #default="scope">{{ typeLabel(scope.row.execution_type) }}</template></el-table-column>
          <el-table-column prop="execution_name" label="执行" min-width="180" />
          <el-table-column label="分类" width="90"><template #default="scope"><el-tag :type="categoryTag(scope.row.category)">{{ categoryLabel(scope.row.category) }}</el-tag></template></el-table-column>
          <el-table-column prop="rule_id" label="规则 ID" min-width="180" />
          <el-table-column prop="reason" label="初步原因" min-width="240" />
          <el-table-column prop="error_code" label="错误码" min-width="190" />
        </el-table>
        <el-empty v-else description="当前没有需要归因的失败执行" />
      </el-card>

      <el-card shadow="never">
        <template #header><div class="card-title"><h2>执行明细</h2><el-tag effect="plain">{{ snapshot.executions.length }} 条</el-tag></div></template>
        <el-table v-if="snapshot.executions.length" :data="snapshot.executions">
          <el-table-column label="类型" width="120"><template #default="scope">{{ typeLabel(scope.row.execution_type) }}</template></el-table-column>
          <el-table-column prop="name" label="名称" min-width="220" />
          <el-table-column label="状态" width="110"><template #default="scope"><el-tag :type="statusTag(scope.row.status)">{{ scope.row.status }}</el-tag></template></el-table-column>
          <el-table-column label="时长" width="110"><template #default="scope">{{ formatDuration(scope.row.duration_ms) }}</template></el-table-column>
          <el-table-column prop="request_summary" label="请求摘要" min-width="280" />
          <el-table-column prop="response_summary" label="响应摘要" min-width="220" />
          <el-table-column prop="error_message" label="稳定失败原因" min-width="220" />
        </el-table>
        <el-empty v-else description="当前工作空间还没有接口执行记录" />
      </el-card>

      <el-card v-if="snapshot.slow_executions.length" shadow="never">
        <template #header><h2>慢执行 Top 10</h2></template>
        <ol class="slow-list">
          <li v-for="item in snapshot.slow_executions" :key="`${item.execution_type}:${item.id}`">
            <span>{{ typeLabel(item.execution_type) }} · {{ item.name }}</span>
            <strong>{{ formatDuration(item.duration_ms) }}</strong>
          </li>
        </ol>
      </el-card>
    </template>
  </main>
</template>

<style scoped>
.reports-page { display: grid; gap: 20px; max-width: 1200px; margin: 0 auto; padding: 36px clamp(20px, 5vw, 72px) 56px; color: var(--app-text); }
.reports-heading, .card-title, .slow-list li { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.heading-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.heading-actions .el-button + .el-button { margin-left: 0; }
.eyebrow { margin: 0 0 6px; color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: .16em; }
h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 8px; }
h2, .reports-heading p { margin-bottom: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.design-summary { display: flex; flex-wrap: wrap; gap: 12px 24px; margin-top: 16px; color: var(--app-muted); }
.metric-note { margin: 12px 0 0; color: var(--app-muted); font-size: 13px; }
.attribution-summary { display: flex; flex-wrap: wrap; gap: 10px 24px; margin: 16px 0; color: var(--app-muted); }
.slow-list { display: grid; gap: 10px; margin: 0; padding-left: 24px; }
@media (max-width: 800px) { .reports-heading { align-items: stretch; flex-direction: column; } .heading-actions { justify-content: flex-start; } .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
