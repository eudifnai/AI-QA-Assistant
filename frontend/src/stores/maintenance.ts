import { defineStore } from "pinia";
import { ref } from "vue";

import {
  createBackup,
  getDiagnostics,
  listBackups,
  type BackupInfo,
  type DiagnosticsReport,
} from "../api/maintenance";

export const useMaintenanceStore = defineStore("maintenance", () => {
  const diagnostics = ref<DiagnosticsReport | null>(null);
  const backups = ref<BackupInfo[]>([]);
  const loading = ref(false);
  const creating = ref(false);
  const error = ref<string | null>(null);

  function messageFrom(reason: unknown): string {
    return reason instanceof Error ? reason.message : "维护操作失败。";
  }

  async function refresh(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const [nextDiagnostics, nextBackups] = await Promise.all([
        getDiagnostics(),
        listBackups(),
      ]);
      diagnostics.value = nextDiagnostics;
      backups.value = nextBackups;
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
    } finally {
      loading.value = false;
    }
  }

  async function create(): Promise<void> {
    creating.value = true;
    error.value = null;
    try {
      const created = await createBackup();
      backups.value = [created, ...backups.value.filter((item) => item.path !== created.path)];
      diagnostics.value = await getDiagnostics();
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      creating.value = false;
    }
  }

  return { diagnostics, backups, loading, creating, error, refresh, create };
});
