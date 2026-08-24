<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElEmpty,
  ElInput,
  ElOption,
  ElProgress,
  ElRadio,
  ElRadioGroup,
  ElSelect,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import type {
  AnalysisDimension,
  AnalysisSeverity,
  AnalysisStartInput,
  AnalysisStatus,
} from "../api/analysis";
import type {
  AutomationRecommendation,
  IssueReviewStatus,
  TestCase,
  TestCaseAutomationType,
  TestCaseBatchStatus,
  TestCaseStatus,
  TestPoint,
  TestPointPriority,
  TestPointStatus,
  TestPointType,
  TraceabilityCoverageStatus,
} from "../api/test-design";
import { useAnalysisStore } from "../stores/analysis";
import { useDocumentStore } from "../stores/documents";
import { useSettingsStore } from "../stores/settings";
import { useTaskEventStore } from "../stores/task-events";
import { useTestDesignStore } from "../stores/test-design";
import { useWorkspaceStore } from "../stores/workspaces";

const workspaceStore = useWorkspaceStore();
const documentStore = useDocumentStore();
const analysisStore = useAnalysisStore();
const testDesignStore = useTestDesignStore();
const settingsStore = useSettingsStore();
const taskEventStore = useTaskEventStore();
const { items: workspaces, activeWorkspace } = storeToRefs(workspaceStore);
const {
  items: documents,
  chunks,
  loading: documentsLoading,
  loadingChunks,
} = storeToRefs(documentStore);
const { items: runs, selected, loading, starting, cancelling, error } = storeToRefs(analysisStore);
const {
  reviews,
  testPoints,
  testCases,
  traceability,
  automationRecommendations,
  loading: designLoading,
  savingReviewId,
  generating,
  savingPointId,
  generatingCases,
  savingCaseId,
  batchUpdatingCases,
  error: designError,
} = storeToRefs(testDesignStore);
const {
  value: settings,
  credentialConfigured,
  credentialLoading,
  credentialError,
} = storeToRefs(settingsStore);
const { state: taskEventState, workspaceId: eventWorkspaceId } = storeToRefs(taskEventStore);
const workspaceId = ref("");
const documentId = ref("");
const chunksLoadedDocumentId = ref("");
const chunksError = ref<string | null>(null);
const cloudConfirmVisible = ref(false);
const cloudRunConsent = ref(false);
const confirmingCloud = ref(false);
const pollPaused = ref(false);
interface PointDraft {
  title: string;
  objective: string;
  test_type: TestPointType;
  priority: TestPointPriority;
  status: TestPointStatus;
  automation_candidate: boolean;
}
interface CaseDraft {
  title: string;
  preconditionsText: string;
  priority: TestPointPriority;
  tagsText: string;
  automation_type: TestCaseAutomationType;
  status: TestCaseStatus;
  steps: Array<{ action: string; expected_result: string }>;
}

const reviewDrafts = ref<
  Record<string, { status: IssueReviewStatus | ""; answer: string }>
>({});
const pointDrafts = ref<Record<string, PointDraft>>({});
const caseDrafts = ref<Record<string, CaseDraft>>({});
const selectedCaseIds = ref<string[]>([]);
const traceabilityFilter = ref<"all" | TraceabilityCoverageStatus>("all");
let pollHandle: number | null = null;

const selectedDocument = computed(
  () => documents.value.find((document) => document.id === documentId.value) ?? null,
);
const isCloudMode = computed(() => settings.value?.model_mode === "cloud");
const chunksReady = computed(
  () =>
    chunksLoadedDocumentId.value === documentId.value &&
    !loadingChunks.value &&
    chunksError.value === null &&
    chunks.value.length > 0,
);
const modelReady = computed(() => {
  const current = settings.value;
  if (current === null || !current.model_name?.trim()) return false;
  if (current.model_mode === "local") {
    return current.model_provider === "ollama" && chunksReady.value;
  }
  return (
    current.model_provider === "openai_compatible" &&
    current.cloud_data_consent &&
    credentialConfigured.value === true &&
    credentialError.value === null &&
    chunksReady.value
  );
});
const canStart = computed(
  () => selectedDocument.value?.latest_version.status === "passed" && modelReady.value,
);
const runActive = computed(() =>
  selected.value !== null && ["pending", "queued", "running"].includes(selected.value.status),
);
const realtimeConnected = computed(
  () => taskEventState.value === "connected" && eventWorkspaceId.value === workspaceId.value,
);
const inputCharacterCount = computed(() =>
  chunks.value.reduce((total, chunk) => total + Array.from(chunk.text).length, 0),
);
const configuredAnalysisEndpoint = computed(() =>
  settings.value === null
    ? ""
    : analysisEndpoint(settings.value.model_provider, settings.value.base_url),
);
const acceptedReviewCount = computed(
  () => reviews.value.filter((review) => review.status === "accepted").length,
);
const confirmedPointCount = computed(
  () => testPoints.value.filter((point) => point.status === "confirmed").length,
);
const traceabilityCounts = computed(() => {
  const covered = traceability.value.filter((row) => row.coverage_status === "covered").length;
  const excluded = traceability.value.filter((row) => row.coverage_status === "excluded").length;
  return {
    total: traceability.value.length,
    covered,
    excluded,
    pending: traceability.value.length - covered - excluded,
  };
});
const filteredTraceability = computed(() =>
  traceabilityFilter.value === "all"
    ? traceability.value
    : traceability.value.filter((row) => row.coverage_status === traceabilityFilter.value),
);

function analysisEndpoint(provider: string, baseUrl: string): string {
  return provider === "openai_compatible"
    ? `${baseUrl.replace(/\/+$/, "")}/chat/completions`
    : baseUrl;
}

const dimensionLabels: Record<AnalysisDimension, string> = {
  completeness: "完整性",
  consistency: "一致性",
  clarity: "清晰度",
  testability: "可测性",
  feasibility: "可行性",
};
const severityLabels: Record<AnalysisSeverity, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};
const testTypeLabels: Record<TestPointType, string> = {
  positive: "正向",
  negative: "异常",
  boundary: "边界",
  state: "状态",
  permission: "权限",
  compatibility: "兼容性",
  performance: "性能",
};
const testPointTypes = Object.keys(testTypeLabels) as TestPointType[];
const testPointPriorities: TestPointPriority[] = ["P0", "P1", "P2", "P3"];
const testPointStatuses: Array<{ value: TestPointStatus; label: string }> = [
  { value: "draft", label: "草稿" },
  { value: "confirmed", label: "已确认" },
  { value: "disabled", label: "已禁用" },
];
const testCaseAutomationTypes: Array<{
  value: TestCaseAutomationType;
  label: string;
}> = [
  { value: "manual", label: "手工" },
  { value: "api", label: "API" },
  { value: "web", label: "Web" },
  { value: "mobile", label: "移动端" },
];
const testCaseStatuses: Array<{ value: TestCaseStatus; label: string }> = [
  { value: "draft", label: "草稿" },
  { value: "confirmed", label: "已确认" },
  { value: "disabled", label: "已禁用" },
];
const traceabilityStatusLabels: Record<TraceabilityCoverageStatus, string> = {
  unreviewed: "未确认",
  excluded: "已排除",
  accepted: "已接受待设计",
  test_point: "已有测试点",
  case_draft: "用例草稿",
  covered: "已覆盖",
  disabled: "已禁用",
};
const traceabilityStatuses = Object.keys(
  traceabilityStatusLabels,
) as TraceabilityCoverageStatus[];

function statusLabel(status: AnalysisStatus): string {
  return {
    pending: "等待中",
    queued: "已排队",
    running: "分析中",
    passed: "已完成",
    failed: "分析失败",
    error: "进程错误",
    cancelled: "已取消",
    timeout: "已超时",
  }[status];
}

function statusType(status: AnalysisStatus): "success" | "warning" | "danger" | "info" {
  if (status === "passed") return "success";
  if (["failed", "error", "timeout"].includes(status)) return "danger";
  if (status === "cancelled") return "warning";
  return "info";
}

function severityType(severity: AnalysisSeverity): "info" | "warning" | "danger" {
  if (severity === "low") return "info";
  if (severity === "medium") return "warning";
  return "danger";
}

function coverageType(
  status: TraceabilityCoverageStatus,
): "success" | "warning" | "danger" | "info" {
  if (status === "covered") return "success";
  if (status === "disabled") return "danger";
  if (["unreviewed", "accepted", "case_draft"].includes(status)) return "warning";
  return "info";
}

function designStatusLabel(status: TestPointStatus | TestCaseStatus): string {
  return { draft: "草稿", confirmed: "已确认", disabled: "已禁用" }[status];
}

async function loadWorkspace(): Promise<void> {
  stopPoll();
  resetCloudConfirmation();
  analysisStore.clear();
  testDesignStore.clear();
  documentId.value = "";
  chunksLoadedDocumentId.value = "";
  chunksError.value = null;
  documentStore.clearChunks();
  if (!workspaceId.value) {
    documentStore.items = [];
    return;
  }
  await documentStore.refresh(workspaceId.value);
  documentId.value =
    documents.value.find((document) => document.latest_version.status === "passed")?.id ?? "";
  await loadDocument();
}

async function loadDocument(): Promise<void> {
  stopPoll();
  resetCloudConfirmation();
  analysisStore.clear();
  testDesignStore.clear();
  pollPaused.value = false;
  chunksLoadedDocumentId.value = "";
  chunksError.value = null;
  documentStore.clearChunks();
  if (!workspaceId.value || !documentId.value) return;
  const requestedDocumentId = documentId.value;
  await Promise.all([
    analysisStore.refresh(workspaceId.value, requestedDocumentId),
    documentStore.loadChunks(workspaceId.value, requestedDocumentId),
  ]);
  if (documentId.value !== requestedDocumentId) return;
  chunksError.value = documentStore.error;
  if (chunksError.value === null) chunksLoadedDocumentId.value = requestedDocumentId;
  schedulePoll();
}

async function start(): Promise<void> {
  if (!canStart.value) return;
  if (isCloudMode.value) {
    cloudRunConsent.value = false;
    cloudConfirmVisible.value = true;
    return;
  }
  await startWithSnapshot(false);
}

function buildStartInput(cloudDataConfirmed: boolean): AnalysisStartInput | null {
  const currentSettings = settings.value;
  const currentDocument = selectedDocument.value;
  const modelName = currentSettings?.model_name?.trim();
  if (currentSettings === null || currentDocument === null || !modelName) return null;
  return {
    expected_version_id: currentDocument.latest_version.id,
    expected_provider: currentSettings.model_provider,
    expected_model_name: modelName,
    expected_base_url: currentSettings.base_url,
    expected_input_chunk_count: chunks.value.length,
    expected_input_character_count: inputCharacterCount.value,
    cloud_data_confirmed: cloudDataConfirmed,
  };
}

async function startWithSnapshot(cloudDataConfirmed: boolean): Promise<void> {
  const input = buildStartInput(cloudDataConfirmed);
  if (input === null) return;
  try {
    pollPaused.value = false;
    await analysisStore.start(workspaceId.value, documentId.value, input);
    schedulePoll();
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

async function confirmCloudAnalysis(): Promise<void> {
  if (!cloudRunConsent.value || confirmingCloud.value || !canStart.value) return;
  confirmingCloud.value = true;
  try {
    await startWithSnapshot(true);
    if (analysisStore.error === null) cloudConfirmVisible.value = false;
  } finally {
    cloudRunConsent.value = false;
    confirmingCloud.value = false;
  }
}

function resetCloudConfirmation(): void {
  cloudConfirmVisible.value = false;
  cloudRunConsent.value = false;
}

async function retryCredentialStatus(): Promise<void> {
  await settingsStore.loadCredentialStatus();
}

async function cancel(): Promise<void> {
  try {
    await analysisStore.cancel(workspaceId.value);
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

function chooseRun(runId: string): void {
  analysisStore.selected = runs.value.find((run) => run.id === runId) ?? null;
  pollPaused.value = false;
  schedulePoll();
}

function reviewDraft(issueId: string): { status: IssueReviewStatus | ""; answer: string } {
  const current = reviewDrafts.value[issueId];
  if (current) return current;
  const saved = reviews.value.find((review) => review.issue_id === issueId);
  const draft: { status: IssueReviewStatus | ""; answer: string } = {
    status: saved?.status ?? "",
    answer: saved?.answer ?? "",
  };
  reviewDrafts.value[issueId] = draft;
  return draft;
}

function sourceIssue(point: TestPoint) {
  return selected.value?.issues.find((issue) => issue.id === point.source_issue_id) ?? null;
}

function pointForIssue(issueId: string): TestPoint | null {
  return testPoints.value.find((point) => point.source_issue_id === issueId) ?? null;
}

function pointDraft(point: TestPoint): PointDraft {
  const current = pointDrafts.value[point.id];
  if (current) return current;
  const draft: PointDraft = {
    title: point.title,
    objective: point.objective,
    test_type: point.test_type,
    priority: point.priority,
    status: point.status,
    automation_candidate: point.automation_candidate,
  };
  pointDrafts.value[point.id] = draft;
  return draft;
}

function caseForPoint(pointId: string): TestCase | null {
  return testCases.value.find((testCase) => testCase.source_test_point_id === pointId) ?? null;
}

function sourcePoint(testCase: TestCase): TestPoint | null {
  return testPoints.value.find((point) => point.id === testCase.source_test_point_id) ?? null;
}

function caseDraft(testCase: TestCase): CaseDraft {
  const current = caseDrafts.value[testCase.id];
  if (current) return current;
  const draft: CaseDraft = {
    title: testCase.title,
    preconditionsText: testCase.preconditions.join("\n"),
    priority: testCase.priority,
    tagsText: testCase.tags.join(", "),
    automation_type: testCase.automation_type,
    status: testCase.status,
    steps: testCase.steps.map((step) => ({
      action: step.action,
      expected_result: step.expected_result,
    })),
  };
  caseDrafts.value[testCase.id] = draft;
  return draft;
}

function recommendationForPoint(pointId: string): AutomationRecommendation | null {
  return (
    automationRecommendations.value.find(
      (recommendation) => recommendation.test_point_id === pointId,
    ) ?? null
  );
}

async function saveIssueReview(issueId: string): Promise<void> {
  const draft = reviewDraft(issueId);
  if (!selected.value || !draft.status || !draft.answer.trim()) return;
  try {
    await testDesignStore.saveReview(workspaceId.value, selected.value.id, issueId, {
      status: draft.status,
      answer: draft.answer.trim(),
    });
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

async function generatePoints(): Promise<void> {
  if (!selected.value || acceptedReviewCount.value === 0) return;
  try {
    await testDesignStore.generate(workspaceId.value, selected.value.id);
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

async function savePoint(pointId: string): Promise<void> {
  const draft = pointDrafts.value[pointId];
  if (!selected.value || !draft || !draft.title.trim() || !draft.objective.trim()) return;
  try {
    await testDesignStore.savePoint(workspaceId.value, selected.value.id, pointId, {
      ...draft,
      title: draft.title.trim(),
      objective: draft.objective.trim(),
    });
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

async function applyPointAutomation(point: TestPoint): Promise<void> {
  const recommendation = recommendationForPoint(point.id);
  if (
    recommendation === null ||
    caseForPoint(point.id) !== null ||
    pointDraft(point).automation_candidate === recommendation.recommended
  ) {
    return;
  }
  pointDraft(point).automation_candidate = recommendation.recommended;
  await savePoint(point.id);
}

async function generateCases(): Promise<void> {
  if (!selected.value || confirmedPointCount.value === 0) return;
  try {
    await testDesignStore.generateCases(workspaceId.value, selected.value.id);
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

function addCaseStep(testCase: TestCase): void {
  caseDraft(testCase).steps.push({ action: "", expected_result: "" });
}

function removeCaseStep(testCase: TestCase, index: number): void {
  const steps = caseDraft(testCase).steps;
  if (steps.length > 1) steps.splice(index, 1);
}

function toggleCaseSelection(caseId: string, selected: string | number | boolean): void {
  if (selected === true) {
    if (!selectedCaseIds.value.includes(caseId)) selectedCaseIds.value.push(caseId);
    return;
  }
  selectedCaseIds.value = selectedCaseIds.value.filter((item) => item !== caseId);
}

async function saveCase(caseId: string): Promise<void> {
  const draft = caseDrafts.value[caseId];
  if (
    !selected.value ||
    !draft ||
    !draft.title.trim() ||
    draft.steps.length === 0 ||
    draft.steps.some((step) => !step.action.trim() || !step.expected_result.trim())
  ) {
    return;
  }
  const preconditions = draft.preconditionsText
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const tags = Array.from(
    new Set(
      draft.tagsText
        .split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
  try {
    await testDesignStore.saveCase(workspaceId.value, selected.value.id, caseId, {
      title: draft.title.trim(),
      preconditions,
      priority: draft.priority,
      tags,
      automation_type: draft.automation_type,
      status: draft.status,
      steps: draft.steps.map((step) => ({
        action: step.action.trim(),
        expected_result: step.expected_result.trim(),
      })),
    });
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

async function applyCaseAutomation(testCase: TestCase): Promise<void> {
  const recommendation = recommendationForPoint(testCase.source_test_point_id);
  if (
    recommendation === null ||
    caseDraft(testCase).automation_type === recommendation.suggested_type
  ) {
    return;
  }
  caseDraft(testCase).automation_type = recommendation.suggested_type;
  await saveCase(testCase.id);
}

async function batchCases(status: TestCaseBatchStatus): Promise<void> {
  if (!selected.value || selectedCaseIds.value.length === 0) return;
  try {
    await testDesignStore.batchCases(workspaceId.value, selected.value.id, {
      test_case_ids: [...selectedCaseIds.value],
      status,
    });
    selectedCaseIds.value = [];
  } catch {
    // The store exposes the backend's safe, recoverable error message.
  }
}

function stopPoll(): void {
  if (pollHandle !== null) window.clearTimeout(pollHandle);
  pollHandle = null;
}

function schedulePoll(): void {
  stopPoll();
  if (!workspaceId.value || !runActive.value || pollPaused.value || realtimeConnected.value) return;
  pollHandle = window.setTimeout(async () => {
    pollHandle = null;
    const succeeded = await analysisStore.refreshSelected(workspaceId.value);
    if (succeeded) schedulePoll();
    else pollPaused.value = true;
  }, 1000);
}

async function retryPolling(): Promise<void> {
  pollPaused.value = false;
  const succeeded = await analysisStore.refreshSelected(workspaceId.value);
  if (succeeded) schedulePoll();
  else pollPaused.value = true;
}

watch(realtimeConnected, schedulePoll);

watch(
  () => [
    settings.value?.model_mode,
    settings.value?.model_provider,
    settings.value?.model_name,
    settings.value?.base_url,
  ],
  resetCloudConfirmation,
);

watch(
  () => [selected.value?.id, selected.value?.status] as const,
  async ([runId, status]) => {
    reviewDrafts.value = {};
    pointDrafts.value = {};
    caseDrafts.value = {};
    selectedCaseIds.value = [];
    traceabilityFilter.value = "all";
    if (!runId || status !== "passed" || !workspaceId.value) {
      testDesignStore.clear();
      return;
    }
    await testDesignStore.load(workspaceId.value, runId);
  },
);

watch(
  [reviews, testPoints, testCases],
  () => {
    for (const review of reviews.value) {
      reviewDrafts.value[review.issue_id] = {
        status: review.status,
        answer: review.answer,
      };
    }
    for (const point of testPoints.value) {
      pointDrafts.value[point.id] = {
        title: point.title,
        objective: point.objective,
        test_type: point.test_type,
        priority: point.priority,
        status: point.status,
        automation_candidate: point.automation_candidate,
      };
    }
    for (const testCase of testCases.value) {
      caseDrafts.value[testCase.id] = {
        title: testCase.title,
        preconditionsText: testCase.preconditions.join("\n"),
        priority: testCase.priority,
        tagsText: testCase.tags.join(", "),
        automation_type: testCase.automation_type,
        status: testCase.status,
        steps: testCase.steps.map((step) => ({
          action: step.action,
          expected_result: step.expected_result,
        })),
      };
    }
  },
  { deep: true },
);

onMounted(async () => {
  if (settings.value === null) await settingsStore.load();
  if (settings.value?.model_mode === "cloud") await settingsStore.loadCredentialStatus();
  if (workspaces.value.length === 0) await workspaceStore.refresh();
  workspaceId.value = activeWorkspace.value?.id ?? workspaces.value[0]?.id ?? "";
  await loadWorkspace();
});

onUnmounted(() => {
  stopPoll();
});
</script>

<template>
  <main class="analysis-page">
    <header class="analysis-heading">
      <div>
        <p class="eyebrow">REQUIREMENT ANALYSIS</p>
        <h1>需求质量分析</h1>
        <p>基于已解析文档生成五维评分、问题建议和可审计来源引用。</p>
      </div>
      <div class="analysis-selectors">
        <el-select
          v-model="workspaceId"
          aria-label="分析工作空间"
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
        <el-select
          v-model="documentId"
          aria-label="分析文档"
          placeholder="选择已解析文档"
          :loading="documentsLoading"
          :disabled="!workspaceId"
          @change="loadDocument"
        >
          <el-option
            v-for="document in documents"
            :key="document.id"
            :label="`${document.name} · v${document.latest_version.version_number}`"
            :value="document.id"
            :disabled="document.latest_version.status !== 'passed'"
          />
        </el-select>
      </div>
    </header>

    <el-alert
      v-if="settings?.model_mode === 'local'"
      :title="`本次仅连接本地 Ollama${settings.model_name ? `（${settings.model_name}）` : ''}；仅发送所选文档版本的稳定引用片段，不会调用云模型或自动回退。`"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="settings"
      :title="`云端分析仅在逐次确认后，将所选文档的全部稳定片段发送到 ${settings.base_url}；不会自动回退到其他模型。`"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="!settings?.model_name"
      title="请先在设置中填写模型名称。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="isCloudMode && !settings?.cloud_data_consent"
      title="请先在设置中确认云端数据边界并保存。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="isCloudMode && credentialConfigured === false"
      title="请先在设置中将 API Key 保存到系统凭据库。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="credentialError"
      :title="credentialError"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button data-testid="retry-credential-status" size="small" @click="retryCredentialStatus">
          重试凭据检查
        </el-button>
      </template>
    </el-alert>
    <el-alert
      v-if="chunksError"
      :title="`无法确认${isCloudMode ? '外发' : '分析'}范围：${chunksError}`"
      type="error"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="chunksLoadedDocumentId === documentId && chunks.length === 0"
      title="所选文档没有可分析的稳定片段，无法开始分析。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon>
      <template v-if="pollPaused" #default>
        <el-button data-testid="retry-analysis-poll" size="small" @click="retryPolling">
          重试获取进度
        </el-button>
      </template>
    </el-alert>
    <el-alert v-if="designError" :title="designError" type="error" :closable="false" show-icon />

    <section class="analysis-actions">
      <div>
        <strong>{{ selectedDocument?.name ?? "尚未选择文档" }}</strong>
        <small v-if="settings">Provider：{{ settings.model_provider }} · {{ settings.base_url }}</small>
      </div>
      <el-button
        data-testid="start-analysis"
        type="primary"
        :disabled="!canStart || runActive"
        :loading="starting || credentialLoading || loadingChunks"
        @click="start"
      >
        开始分析
      </el-button>
    </section>

    <section class="analysis-layout" v-loading="loading">
      <el-card shadow="never">
        <template #header><h2>分析记录</h2></template>
        <el-empty v-if="runs.length === 0" description="当前文档还没有分析记录" />
        <div v-else class="run-list">
          <button
            v-for="run in runs"
            :key="run.id"
            type="button"
            class="run-item"
            :class="{ selected: selected?.id === run.id }"
            @click="chooseRun(run.id)"
          >
            <span><strong>{{ run.model_name }}</strong><el-tag :type="statusType(run.status)" size="small">{{ statusLabel(run.status) }}</el-tag></span>
            <small>{{ new Date(run.created_at).toLocaleString() }}</small>
            <el-progress
              v-if="['pending', 'queued', 'running'].includes(run.status)"
              :percentage="run.progress"
              :stroke-width="6"
            />
          </button>
        </div>
      </el-card>

      <div class="analysis-results">
        <el-card shadow="never">
          <template #header>
            <div class="result-heading">
              <h2>分析结果</h2>
              <el-button
                v-if="runActive"
                type="danger"
                plain
                :loading="cancelling"
                @click="cancel"
              >取消分析</el-button>
            </div>
          </template>
          <el-empty v-if="!selected" description="选择或发起一次分析" />
          <template v-else>
            <div class="run-metadata">
              <span>Provider：{{ selected.provider }}</span>
              <span>模型：{{ selected.model_name }}</span>
              <span>Endpoint：{{ analysisEndpoint(selected.provider, selected.base_url) }}</span>
              <span>
                输入范围：全部 {{ selected.input_chunk_count }} 个片段，共
                {{ selected.input_character_count }} 个字符
              </span>
              <span v-if="selected.cloud_data_confirmed_at">
                云端确认：{{ new Date(selected.cloud_data_confirmed_at).toLocaleString() }}
              </span>
            </div>
            <el-alert
              v-if="selected.error_message"
              :title="selected.error_message"
              type="error"
              :closable="false"
              show-icon
            />
            <div v-if="selected.status === 'passed'" class="score-summary">
              <div class="overall-score"><strong>{{ selected.overall_score }}</strong><span>综合评分</span></div>
              <article v-for="score in selected.scores" :key="score.dimension" class="dimension-score">
                <header><strong>{{ dimensionLabels[score.dimension] }}</strong><span>{{ score.score }}</span></header>
                <el-progress :percentage="score.score" :show-text="false" />
                <p>{{ score.summary }}</p>
              </article>
            </div>
            <el-progress
              v-else-if="runActive"
              :percentage="selected.progress"
              :status="selected.progress === 100 ? 'success' : undefined"
            />
          </template>
        </el-card>

        <el-card v-if="selected?.status === 'passed'" shadow="never">
          <template #header><h2>发现的问题（{{ selected.issues.length }}）</h2></template>
          <el-empty v-if="selected.issues.length === 0" description="未发现结构化问题" />
          <div v-else class="issue-list">
            <article v-for="issue in selected.issues" :key="issue.id" class="issue-card">
              <header>
                <div><el-tag :type="severityType(issue.severity)" size="small">{{ severityLabels[issue.severity] }}</el-tag><el-tag type="info" size="small">{{ dimensionLabels[issue.dimension] }}</el-tag></div>
                <strong>{{ issue.title }}</strong>
              </header>
              <p>{{ issue.description }}</p>
              <dl>
                <div><dt>影响</dt><dd>{{ issue.impact }}</dd></div>
                <div><dt>建议</dt><dd>{{ issue.suggestion }}</dd></div>
                <div><dt>待确认</dt><dd>{{ issue.question }}</dd></div>
              </dl>
              <div class="citations">
                <strong>来源引用</strong>
                <blockquote v-for="citation in issue.citations" :key="citation.chunk_id">
                  <span>{{ citation.locator }} · {{ citation.chunk_id }}</span>
                  <p>{{ citation.text }}</p>
                </blockquote>
              </div>
              <div class="issue-review">
                <strong>人工确认</strong>
                <el-radio-group
                  v-model="reviewDraft(issue.id).status"
                  :disabled="pointForIssue(issue.id) !== null"
                >
                  <el-radio
                    value="accepted"
                    :data-testid="`review-accepted-${issue.id}`"
                  >纳入测试设计</el-radio>
                  <el-radio
                    value="rejected"
                    :data-testid="`review-rejected-${issue.id}`"
                  >无需覆盖</el-radio>
                </el-radio-group>
                <el-input
                  v-model="reviewDraft(issue.id).answer"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                  show-word-limit
                  :disabled="pointForIssue(issue.id) !== null"
                  placeholder="填写确认结论或不纳入原因"
                  :data-testid="`review-answer-${issue.id}`"
                />
                <div class="review-actions">
                  <small v-if="pointForIssue(issue.id)">已生成测试点，确认结论已锁定。</small>
                  <el-button
                    type="primary"
                    plain
                    :disabled="
                      pointForIssue(issue.id) !== null ||
                      !reviewDraft(issue.id).status ||
                      !reviewDraft(issue.id).answer.trim()
                    "
                    :loading="savingReviewId === issue.id"
                    :data-testid="`save-review-${issue.id}`"
                    @click="saveIssueReview(issue.id)"
                  >保存确认</el-button>
                </div>
              </div>
            </article>
          </div>
        </el-card>

        <el-card v-if="selected?.status === 'passed'" v-loading="designLoading" shadow="never">
          <template #header>
            <div class="result-heading">
              <div>
                <h2>测试点（{{ testPoints.length }}）</h2>
                <small>已接受 {{ acceptedReviewCount }} 个问题；每个来源问题最多生成一个测试点。</small>
              </div>
              <el-button
                type="primary"
                :disabled="acceptedReviewCount === 0"
                :loading="generating"
                data-testid="generate-test-points"
                @click="generatePoints"
              >生成测试点</el-button>
            </div>
          </template>
          <el-empty v-if="testPoints.length === 0" description="确认问题后可生成可编辑测试点" />
          <div v-else class="test-point-list">
            <article
              v-for="point in testPoints"
              :key="point.id"
              class="test-point-card"
            >
              <template>
                <strong>来源：{{ sourceIssue(point)?.title ?? point.source_issue_id }}</strong>
                <el-input
                  v-model="pointDraft(point).title"
                  maxlength="500"
                  show-word-limit
                  :disabled="caseForPoint(point.id) !== null"
                  :data-testid="`point-title-${point.id}`"
                />
                <el-input
                  v-model="pointDraft(point).objective"
                  type="textarea"
                  :rows="4"
                  maxlength="4000"
                  show-word-limit
                  :disabled="caseForPoint(point.id) !== null"
                />
                <div
                  v-if="recommendationForPoint(point.id)"
                  class="automation-recommendation"
                >
                  <div>
                    <el-tag
                      :type="recommendationForPoint(point.id)?.recommended ? 'success' : 'info'"
                      size="small"
                    >
                      {{
                        recommendationForPoint(point.id)?.recommended
                          ? `建议 ${recommendationForPoint(point.id)?.suggested_type.toUpperCase()} 自动化`
                          : "建议人工评审"
                      }}
                    </el-tag>
                    <small>规则：{{ recommendationForPoint(point.id)?.rule_id }}</small>
                    <p>{{ recommendationForPoint(point.id)?.reason }}</p>
                  </div>
                  <el-button
                    v-if="caseForPoint(point.id) === null"
                    plain
                    :disabled="
                      pointDraft(point).automation_candidate ===
                      recommendationForPoint(point.id)?.recommended
                    "
                    :loading="savingPointId === point.id"
                    :data-testid="`apply-point-automation-${point.id}`"
                    @click="applyPointAutomation(point)"
                  >
                    {{
                      pointDraft(point).automation_candidate ===
                      recommendationForPoint(point.id)?.recommended
                        ? "已应用建议"
                        : "应用建议"
                    }}
                  </el-button>
                </div>
                <div class="point-fields">
                  <el-select
                    v-model="pointDraft(point).test_type"
                    aria-label="测试类型"
                    :disabled="caseForPoint(point.id) !== null"
                  >
                    <el-option
                      v-for="type in testPointTypes"
                      :key="type"
                      :label="testTypeLabels[type]"
                      :value="type"
                    />
                  </el-select>
                  <el-select
                    v-model="pointDraft(point).priority"
                    aria-label="优先级"
                    :disabled="caseForPoint(point.id) !== null"
                  >
                    <el-option
                      v-for="priority in testPointPriorities"
                      :key="priority"
                      :label="priority"
                      :value="priority"
                    />
                  </el-select>
                  <el-select
                    v-model="pointDraft(point).status"
                    aria-label="测试点状态"
                    :disabled="caseForPoint(point.id) !== null"
                  >
                    <el-option
                      v-for="item in testPointStatuses"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                  <el-checkbox
                    v-model="pointDraft(point).automation_candidate"
                    :disabled="caseForPoint(point.id) !== null"
                  >
                    自动化候选
                  </el-checkbox>
                </div>
                <div v-if="sourceIssue(point)" class="citations">
                  <blockquote
                    v-for="citation in sourceIssue(point)?.citations"
                    :key="citation.chunk_id"
                  >
                    <span>{{ citation.locator }} · {{ citation.chunk_id }}</span>
                    <p>{{ citation.text }}</p>
                  </blockquote>
                </div>
                <div class="review-actions">
                  <small v-if="caseForPoint(point.id)">已生成测试用例，测试点已锁定。</small>
                  <small v-else>来源问题：{{ point.source_issue_id }}</small>
                  <el-button
                    type="primary"
                    :loading="savingPointId === point.id"
                    :disabled="
                      caseForPoint(point.id) !== null ||
                      !pointDraft(point).title.trim() ||
                      !pointDraft(point).objective.trim()
                    "
                    :data-testid="`save-test-point-${point.id}`"
                    @click="savePoint(point.id)"
                  >保存测试点</el-button>
                </div>
              </template>
            </article>
          </div>
        </el-card>

        <el-card v-if="selected?.status === 'passed'" shadow="never">
          <template #header>
            <div class="result-heading">
              <div>
                <h2>测试用例（{{ testCases.length }}）</h2>
                <small>
                  已确认 {{ confirmedPointCount }} 个测试点；每个来源测试点最多生成一个结构化用例。
                </small>
              </div>
              <el-button
                type="primary"
                :disabled="confirmedPointCount === 0"
                :loading="generatingCases"
                data-testid="generate-test-cases"
                @click="generateCases"
              >生成测试用例</el-button>
            </div>
          </template>
          <el-empty
            v-if="testCases.length === 0"
            description="确认测试点后可生成本地结构化用例草稿"
          />
          <template v-else>
            <div class="case-batch-actions">
              <small>已选择 {{ selectedCaseIds.length }} 项</small>
              <div>
                <el-button
                  :disabled="selectedCaseIds.length === 0"
                  :loading="batchUpdatingCases"
                  data-testid="batch-confirm-test-cases"
                  @click="batchCases('confirmed')"
                >批量确认</el-button>
                <el-button
                  :disabled="selectedCaseIds.length === 0"
                  :loading="batchUpdatingCases"
                  data-testid="batch-disable-test-cases"
                  @click="batchCases('disabled')"
                >批量禁用</el-button>
              </div>
            </div>
            <div class="test-case-list">
              <article v-for="testCase in testCases" :key="testCase.id" class="test-case-card">
                <header>
                  <el-checkbox
                    :model-value="selectedCaseIds.includes(testCase.id)"
                    :data-testid="`select-test-case-${testCase.id}`"
                    @change="toggleCaseSelection(testCase.id, $event)"
                  >选择</el-checkbox>
                  <strong>
                    来源测试点：{{ sourcePoint(testCase)?.title ?? testCase.source_test_point_id }}
                  </strong>
                </header>
                <el-input
                  v-model="caseDraft(testCase).title"
                  maxlength="500"
                  show-word-limit
                  placeholder="用例标题"
                  :data-testid="`case-title-${testCase.id}`"
                />
                <el-input
                  v-model="caseDraft(testCase).preconditionsText"
                  type="textarea"
                  :rows="3"
                  maxlength="10000"
                  show-word-limit
                  placeholder="前置条件，每行一项"
                />
                <div
                  v-if="recommendationForPoint(testCase.source_test_point_id)"
                  class="automation-recommendation"
                >
                  <div>
                    <el-tag
                      :type="
                        recommendationForPoint(testCase.source_test_point_id)?.recommended
                          ? 'success'
                          : 'info'
                      "
                      size="small"
                    >
                      建议
                      {{
                        recommendationForPoint(
                          testCase.source_test_point_id,
                        )?.suggested_type.toUpperCase()
                      }}
                    </el-tag>
                    <small>
                      规则：{{ recommendationForPoint(testCase.source_test_point_id)?.rule_id }}
                    </small>
                    <p>{{ recommendationForPoint(testCase.source_test_point_id)?.reason }}</p>
                  </div>
                  <el-button
                    plain
                    :disabled="
                      caseDraft(testCase).automation_type ===
                      recommendationForPoint(testCase.source_test_point_id)?.suggested_type
                    "
                    :loading="savingCaseId === testCase.id"
                    :data-testid="`apply-case-automation-${testCase.id}`"
                    @click="applyCaseAutomation(testCase)"
                  >
                    {{
                      caseDraft(testCase).automation_type ===
                      recommendationForPoint(testCase.source_test_point_id)?.suggested_type
                        ? "已应用建议"
                        : "应用建议"
                    }}
                  </el-button>
                </div>
                <div class="case-fields">
                  <el-select v-model="caseDraft(testCase).priority" aria-label="用例优先级">
                    <el-option
                      v-for="priority in testPointPriorities"
                      :key="priority"
                      :label="priority"
                      :value="priority"
                    />
                  </el-select>
                  <el-select
                    v-model="caseDraft(testCase).automation_type"
                    aria-label="自动化类型"
                  >
                    <el-option
                      v-for="item in testCaseAutomationTypes"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                  <el-select v-model="caseDraft(testCase).status" aria-label="用例状态">
                    <el-option
                      v-for="item in testCaseStatuses"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </div>
                <el-input
                  v-model="caseDraft(testCase).tagsText"
                  maxlength="1000"
                  placeholder="标签，使用逗号分隔"
                />
                <div class="case-steps">
                  <strong>执行步骤</strong>
                  <article
                    v-for="(step, index) in caseDraft(testCase).steps"
                    :key="index"
                    class="case-step"
                  >
                    <span>{{ index + 1 }}</span>
                    <el-input
                      v-model="step.action"
                      type="textarea"
                      :rows="2"
                      maxlength="4000"
                      placeholder="操作"
                      :data-testid="`case-step-action-${testCase.id}-${index}`"
                    />
                    <el-input
                      v-model="step.expected_result"
                      type="textarea"
                      :rows="2"
                      maxlength="4000"
                      placeholder="预期结果"
                      :data-testid="`case-step-expected-${testCase.id}-${index}`"
                    />
                    <el-button
                      text
                      type="danger"
                      :disabled="caseDraft(testCase).steps.length === 1"
                      @click="removeCaseStep(testCase, index)"
                    >删除</el-button>
                  </article>
                  <el-button plain @click="addCaseStep(testCase)">添加步骤</el-button>
                </div>
                <div class="review-actions">
                  <small>来源测试点：{{ testCase.source_test_point_id }}</small>
                  <el-button
                    type="primary"
                    :loading="savingCaseId === testCase.id"
                    :disabled="
                      !caseDraft(testCase).title.trim() ||
                      caseDraft(testCase).steps.length === 0 ||
                      caseDraft(testCase).steps.some(
                        (step) => !step.action.trim() || !step.expected_result.trim(),
                      )
                    "
                    :data-testid="`save-test-case-${testCase.id}`"
                    @click="saveCase(testCase.id)"
                  >保存测试用例</el-button>
                </div>
              </article>
            </div>
          </template>
        </el-card>

        <el-card v-if="selected?.status === 'passed'" shadow="never">
          <template #header>
            <div class="result-heading traceability-heading">
              <div>
                <h2>需求追踪矩阵</h2>
                <small>由当前分析运行的冻结问题、确认结论、测试点和测试用例实时派生。</small>
              </div>
              <label class="traceability-filter">
                <span>覆盖状态</span>
                <select v-model="traceabilityFilter" data-testid="traceability-filter">
                  <option value="all">全部</option>
                  <option
                    v-for="status in traceabilityStatuses"
                    :key="status"
                    :value="status"
                  >{{ traceabilityStatusLabels[status] }}</option>
                </select>
              </label>
            </div>
          </template>
          <div class="traceability-summary">
            <span>总问题 {{ traceabilityCounts.total }}</span>
            <span class="covered">已覆盖 {{ traceabilityCounts.covered }}</span>
            <span class="pending">待处理 {{ traceabilityCounts.pending }}</span>
            <span>已排除 {{ traceabilityCounts.excluded }}</span>
          </div>
          <el-empty
            v-if="traceability.length === 0"
            description="当前分析没有可追踪问题"
          />
          <el-empty
            v-else-if="filteredTraceability.length === 0"
            description="当前筛选条件下没有追踪记录"
          />
          <div v-else class="traceability-table-wrap">
            <table class="traceability-table">
              <thead>
                <tr>
                  <th>分析问题 / 需求引用</th>
                  <th>人工结论</th>
                  <th>测试点</th>
                  <th>测试用例</th>
                  <th>覆盖状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in filteredTraceability"
                  :key="row.issue_id"
                  :data-testid="`traceability-row-${row.issue_id}`"
                >
                  <td>
                    <strong>{{ row.issue_title }}</strong>
                    <div class="traceability-tags">
                      <el-tag size="small" type="info">{{ dimensionLabels[row.dimension] }}</el-tag>
                      <el-tag size="small" :type="severityType(row.severity)">
                        {{ severityLabels[row.severity] }}
                      </el-tag>
                    </div>
                    <div v-if="row.citations.length" class="traceability-citations">
                      <span v-for="citation in row.citations" :key="citation.chunk_id">
                        {{ citation.locator }} · {{ citation.chunk_id }}
                      </span>
                    </div>
                    <small v-else>无稳定原文引用</small>
                  </td>
                  <td>
                    <template v-if="row.review_status">
                      <strong>{{ row.review_status === "accepted" ? "纳入测试设计" : "无需覆盖" }}</strong>
                      <small>{{ row.review_answer }}</small>
                    </template>
                    <small v-else>尚未人工确认</small>
                  </td>
                  <td>
                    <template v-if="row.test_point_id && row.test_point_status">
                      <strong>{{ row.test_point_title }}</strong>
                      <small>{{ designStatusLabel(row.test_point_status) }} · {{ row.test_point_id }}</small>
                    </template>
                    <small v-else>尚未生成</small>
                  </td>
                  <td>
                    <template v-if="row.test_case_id && row.test_case_status">
                      <strong>{{ row.test_case_title }}</strong>
                      <small>{{ designStatusLabel(row.test_case_status) }} · {{ row.test_case_id }}</small>
                    </template>
                    <small v-else>尚未生成</small>
                  </td>
                  <td>
                    <el-tag :type="coverageType(row.coverage_status)">
                      {{ traceabilityStatusLabels[row.coverage_status] }}
                    </el-tag>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </el-card>
      </div>
    </section>

    <el-dialog
      v-model="cloudConfirmVisible"
      title="即将发送到云端模型"
      width="min(640px, 92vw)"
      :close-on-click-modal="false"
      @closed="cloudRunConsent = false"
    >
      <el-alert
        title="以下完整范围会发送到所配置的 OpenAI-compatible 服务；本次确认仅对这一次分析有效。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-descriptions class="cloud-scope" :column="1" border>
        <el-descriptions-item label="Provider">{{ settings?.model_provider }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ settings?.model_name }}</el-descriptions-item>
        <el-descriptions-item label="Endpoint">{{ configuredAnalysisEndpoint }}</el-descriptions-item>
        <el-descriptions-item label="文档">
          {{ selectedDocument?.name }} · v{{ selectedDocument?.latest_version.version_number }}
        </el-descriptions-item>
        <el-descriptions-item label="数据范围">
          全部 {{ chunks.length }} 个片段，共 {{ inputCharacterCount }} 个字符
        </el-descriptions-item>
      </el-descriptions>
      <el-checkbox v-model="cloudRunConsent" data-testid="cloud-run-consent">
        我确认将上述数据发送到该云端 Provider，并仅用于本次分析。
      </el-checkbox>
      <template #footer>
        <el-button data-testid="cancel-cloud-analysis" @click="resetCloudConfirmation">
          取消
        </el-button>
        <el-button
          data-testid="confirm-cloud-analysis"
          type="primary"
          :disabled="!cloudRunConsent || confirmingCloud"
          :loading="confirmingCloud"
          @click="confirmCloudAnalysis"
        >
          确认并发送
        </el-button>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.analysis-page { display: grid; gap: 20px; max-width: 1240px; margin: 0 auto; padding: 36px clamp(20px, 5vw, 72px) 56px; color: var(--app-text); }
.analysis-heading, .analysis-actions, .result-heading, .run-item span, .dimension-score header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.analysis-selectors { display: flex; gap: 10px; }
.analysis-selectors .el-select { width: 230px; }
.eyebrow { margin: 0 0 6px; color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: 0.16em; }
h1, h2, p { margin-top: 0; }
h1, h2, .analysis-heading p { margin-bottom: 0; }
h2 { font-size: 18px; }
.analysis-actions { padding: 16px 18px; border: 1px solid var(--app-border); border-radius: 12px; background: var(--app-surface); }
.analysis-actions div { display: grid; gap: 4px; }
.analysis-actions small, .run-item small, dt, blockquote span { color: var(--app-muted); }
.run-metadata { display: grid; gap: 5px; margin-bottom: 16px; color: var(--app-muted); font-size: 13px; overflow-wrap: anywhere; }
.cloud-scope { margin: 16px 0; }
.analysis-layout { display: grid; grid-template-columns: minmax(240px, 0.55fr) minmax(520px, 1.45fr); gap: 20px; align-items: start; }
.analysis-results, .run-list, .issue-list, .test-point-list, .test-case-list, .case-steps { display: grid; gap: 14px; }
.run-item { display: grid; gap: 8px; width: 100%; padding: 14px; border: 1px solid var(--app-border); border-radius: 10px; color: var(--app-text); background: var(--app-surface); text-align: left; cursor: pointer; }
.run-item.selected { border-color: #409eff; }
.run-item span { align-items: flex-start; }
.score-summary { display: grid; grid-template-columns: 140px repeat(2, minmax(180px, 1fr)); gap: 12px; }
.overall-score, .dimension-score { padding: 14px; border: 1px solid var(--app-border); border-radius: 10px; }
.overall-score { display: grid; align-content: center; justify-items: center; background: color-mix(in srgb, #409eff 8%, var(--app-surface)); }
.overall-score strong { color: #409eff; font-size: 38px; }
.overall-score span, .dimension-score p { color: var(--app-muted); }
.dimension-score p { margin: 8px 0 0; font-size: 13px; }
.issue-card { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--app-border); border-radius: 12px; }
.issue-card > header { display: grid; gap: 9px; }
.issue-card > header div { display: flex; gap: 6px; }
.issue-card > p { margin-bottom: 0; }
dl { display: grid; gap: 8px; margin: 0; }
dl div { display: grid; grid-template-columns: 64px 1fr; gap: 8px; }
dd { margin: 0; }
.citations { display: grid; gap: 8px; }
.issue-review, .test-point-card, .test-case-card { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--app-border); border-radius: 10px; background: var(--app-background); }
.review-actions, .point-fields, .case-fields, .case-batch-actions, .test-case-card > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.review-actions small { color: var(--app-muted); }
.point-fields .el-select, .case-fields .el-select { width: 150px; }
.case-batch-actions { margin-bottom: 14px; }
.case-batch-actions small { color: var(--app-muted); }
.case-step { display: grid; grid-template-columns: 28px minmax(0, 1fr) minmax(0, 1fr) auto; gap: 10px; align-items: start; }
.case-step > span { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; color: #409eff; background: color-mix(in srgb, #409eff 10%, var(--app-surface)); font-weight: 700; }
.automation-recommendation { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px; border: 1px dashed color-mix(in srgb, #409eff 45%, var(--app-border)); border-radius: 9px; background: color-mix(in srgb, #409eff 5%, var(--app-surface)); }
.automation-recommendation > div { display: grid; gap: 5px; }
.automation-recommendation small { color: var(--app-muted); }
.automation-recommendation p { margin: 0; color: var(--app-muted); font-size: 13px; }
.traceability-filter { display: grid; gap: 4px; color: var(--app-muted); font-size: 12px; }
.traceability-filter select { min-width: 150px; padding: 8px 10px; border: 1px solid var(--app-border); border-radius: 8px; color: var(--app-text); background: var(--app-surface); }
.traceability-summary { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.traceability-summary span { padding: 7px 10px; border-radius: 999px; color: var(--app-muted); background: var(--app-background); font-size: 13px; }
.traceability-summary .covered { color: #529b2e; }
.traceability-summary .pending { color: #b88230; }
.traceability-table-wrap { overflow-x: auto; }
.traceability-table { width: 100%; min-width: 920px; border-collapse: collapse; }
.traceability-table th, .traceability-table td { padding: 12px; border: 1px solid var(--app-border); text-align: left; vertical-align: top; }
.traceability-table th { color: var(--app-muted); background: var(--app-background); font-size: 13px; }
.traceability-table td { min-width: 150px; }
.traceability-table td:first-child { min-width: 230px; }
.traceability-table td strong, .traceability-table td small { display: block; }
.traceability-table td small { margin-top: 6px; color: var(--app-muted); }
.traceability-tags { display: flex; gap: 5px; margin-top: 7px; }
.traceability-citations { display: grid; gap: 3px; margin-top: 8px; color: var(--app-muted); font-size: 12px; }
blockquote { margin: 0; padding: 10px 12px; border-left: 3px solid #409eff; background: var(--app-background); }
blockquote p { margin: 5px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 900px) { .analysis-heading, .analysis-selectors, .point-fields, .case-fields, .case-batch-actions, .traceability-heading, .automation-recommendation { align-items: stretch; flex-direction: column; } .analysis-selectors .el-select, .point-fields .el-select, .case-fields .el-select, .analysis-layout, .traceability-filter select { width: 100%; } .analysis-layout { grid-template-columns: 1fr; } .score-summary, .case-step { grid-template-columns: 1fr; } }
</style>
