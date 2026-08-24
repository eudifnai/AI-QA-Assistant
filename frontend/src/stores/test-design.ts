import { defineStore } from "pinia";
import { ref } from "vue";

import {
  batchUpdateTestCases,
  generateTestCases,
  generateTestPoints,
  getTestDesign,
  reviewAnalysisIssue,
  updateTestCase,
  updateTestPoint,
  type IssueReview,
  type IssueReviewInput,
  type AutomationRecommendation,
  type TestCase,
  type TestCaseBatchStatusInput,
  type TestCaseUpdateInput,
  type TraceabilityRow,
  type TestPoint,
  type TestPointUpdateInput,
} from "../api/test-design";

export const useTestDesignStore = defineStore("test-design", () => {
  const runId = ref("");
  const reviews = ref<IssueReview[]>([]);
  const testPoints = ref<TestPoint[]>([]);
  const testCases = ref<TestCase[]>([]);
  const traceability = ref<TraceabilityRow[]>([]);
  const automationRecommendations = ref<AutomationRecommendation[]>([]);
  const loading = ref(false);
  const savingReviewId = ref<string | null>(null);
  const generating = ref(false);
  const savingPointId = ref<string | null>(null);
  const generatingCases = ref(false);
  const savingCaseId = ref<string | null>(null);
  const batchUpdatingCases = ref(false);
  const error = ref<string | null>(null);
  let contextGeneration = 0;

  function message(reason: unknown): string {
    return reason instanceof Error ? reason.message : "测试设计操作失败。";
  }

  async function refreshDerivedState(
    workspaceId: string,
    selectedRunId: string,
    requestGeneration: number,
  ): Promise<void> {
    try {
      const snapshot = await getTestDesign(workspaceId, selectedRunId);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      traceability.value = snapshot.traceability;
      automationRecommendations.value = snapshot.automation_recommendations;
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = `操作已完成，但追踪矩阵和自动化建议刷新失败：${message(reason)}`;
    }
  }

  async function load(workspaceId: string, selectedRunId: string): Promise<void> {
    const requestGeneration = ++contextGeneration;
    runId.value = selectedRunId;
    reviews.value = [];
    testPoints.value = [];
    testCases.value = [];
    traceability.value = [];
    automationRecommendations.value = [];
    savingReviewId.value = null;
    generating.value = false;
    savingPointId.value = null;
    generatingCases.value = false;
    savingCaseId.value = null;
    batchUpdatingCases.value = false;
    loading.value = true;
    error.value = null;
    try {
      const snapshot = await getTestDesign(workspaceId, selectedRunId);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      reviews.value = snapshot.reviews;
      testPoints.value = snapshot.test_points;
      testCases.value = snapshot.test_cases;
      traceability.value = snapshot.traceability;
      automationRecommendations.value = snapshot.automation_recommendations;
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
    } finally {
      if (requestGeneration === contextGeneration) loading.value = false;
    }
  }

  async function saveReview(
    workspaceId: string,
    selectedRunId: string,
    issueId: string,
    input: IssueReviewInput,
  ): Promise<void> {
    const requestGeneration = contextGeneration;
    savingReviewId.value = issueId;
    error.value = null;
    try {
      const saved = await reviewAnalysisIssue(workspaceId, selectedRunId, issueId, input);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      reviews.value = [saved, ...reviews.value.filter((item) => item.issue_id !== issueId)];
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) savingReviewId.value = null;
    }
  }

  async function generate(workspaceId: string, selectedRunId: string): Promise<void> {
    const requestGeneration = contextGeneration;
    generating.value = true;
    error.value = null;
    try {
      const points = await generateTestPoints(workspaceId, selectedRunId);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      testPoints.value = points;
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) generating.value = false;
    }
  }

  async function savePoint(
    workspaceId: string,
    selectedRunId: string,
    pointId: string,
    input: TestPointUpdateInput,
  ): Promise<void> {
    const requestGeneration = contextGeneration;
    savingPointId.value = pointId;
    error.value = null;
    try {
      const saved = await updateTestPoint(workspaceId, selectedRunId, pointId, input);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      testPoints.value = testPoints.value.map((item) => (item.id === pointId ? saved : item));
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) savingPointId.value = null;
    }
  }

  async function generateCases(workspaceId: string, selectedRunId: string): Promise<void> {
    const requestGeneration = contextGeneration;
    generatingCases.value = true;
    error.value = null;
    try {
      const cases = await generateTestCases(workspaceId, selectedRunId);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      testCases.value = cases;
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) generatingCases.value = false;
    }
  }

  async function saveCase(
    workspaceId: string,
    selectedRunId: string,
    caseId: string,
    input: TestCaseUpdateInput,
  ): Promise<void> {
    const requestGeneration = contextGeneration;
    savingCaseId.value = caseId;
    error.value = null;
    try {
      const saved = await updateTestCase(workspaceId, selectedRunId, caseId, input);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      testCases.value = testCases.value.map((item) => (item.id === caseId ? saved : item));
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) savingCaseId.value = null;
    }
  }

  async function batchCases(
    workspaceId: string,
    selectedRunId: string,
    input: TestCaseBatchStatusInput,
  ): Promise<void> {
    const requestGeneration = contextGeneration;
    batchUpdatingCases.value = true;
    error.value = null;
    try {
      const saved = await batchUpdateTestCases(workspaceId, selectedRunId, input);
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      const savedById = new Map(saved.map((item) => [item.id, item]));
      testCases.value = testCases.value.map((item) => savedById.get(item.id) ?? item);
      await refreshDerivedState(workspaceId, selectedRunId, requestGeneration);
    } catch (reason: unknown) {
      if (requestGeneration !== contextGeneration || runId.value !== selectedRunId) return;
      error.value = message(reason);
      throw reason;
    } finally {
      if (requestGeneration === contextGeneration) batchUpdatingCases.value = false;
    }
  }

  function clear(): void {
    contextGeneration += 1;
    runId.value = "";
    reviews.value = [];
    testPoints.value = [];
    testCases.value = [];
    traceability.value = [];
    automationRecommendations.value = [];
    loading.value = false;
    savingReviewId.value = null;
    generating.value = false;
    savingPointId.value = null;
    generatingCases.value = false;
    savingCaseId.value = null;
    batchUpdatingCases.value = false;
    error.value = null;
  }

  return {
    runId,
    reviews,
    testPoints,
    testCases,
    traceability,
    automationRecommendations,
    loading,
    savingReviewId,
    generating,
    savingPointId,
    generatingCases,
    savingCaseId,
    batchUpdatingCases,
    error,
    load,
    saveReview,
    generate,
    savePoint,
    generateCases,
    saveCase,
    batchCases,
    clear,
  };
});
