import { defineStore } from "pinia";
import { ref } from "vue";

import { fetchHealth } from "../api/health";

export type HealthUiStatus = "idle" | "loading" | "online" | "offline";

export const useHealthStore = defineStore("health", () => {
  const status = ref<HealthUiStatus>("idle");
  const version = ref<string | null>(null);
  const error = ref<string | null>(null);

  async function refresh(): Promise<void> {
    status.value = "loading";
    error.value = null;
    try {
      const health = await fetchHealth();
      status.value = "online";
      version.value = health.version;
    } catch (reason: unknown) {
      status.value = "offline";
      version.value = null;
      error.value = reason instanceof Error ? reason.message : "无法检查本地后端状态。";
    }
  }

  return { status, version, error, refresh };
});

