import { defineStore } from "pinia";
import { ref } from "vue";

import {
  clearModelCredential,
  getCredentialStatus,
  getSettings,
  saveModelCredential,
  updateSettings,
  type AppSettings,
  type SettingsUpdateInput,
} from "../api/settings";

function applyTheme(theme: AppSettings["theme"]): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export const useSettingsStore = defineStore("settings", () => {
  const value = ref<AppSettings | null>(null);
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const credentialConfigured = ref<boolean | null>(null);
  const credentialLoading = ref(false);
  const credentialSaving = ref(false);
  const credentialError = ref<string | null>(null);
  let currentLoad: Promise<void> | null = null;

  function messageFrom(reason: unknown): string {
    return reason instanceof Error ? reason.message : "设置操作失败。";
  }

  async function performLoad(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      value.value = await getSettings();
      applyTheme(value.value.theme);
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
    } finally {
      loading.value = false;
    }
  }

  function load(): Promise<void> {
    if (currentLoad !== null) {
      return currentLoad;
    }
    currentLoad = performLoad().finally(() => {
      currentLoad = null;
    });
    return currentLoad;
  }

  async function save(input: SettingsUpdateInput): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      value.value = await updateSettings({
        theme: input.theme,
        model_mode: input.model_mode,
        model_provider: input.model_provider,
        model_name: input.model_name,
        base_url: input.base_url,
        cloud_data_consent: input.cloud_data_consent,
      });
      applyTheme(value.value.theme);
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      saving.value = false;
    }
  }

  async function loadCredentialStatus(): Promise<void> {
    credentialLoading.value = true;
    credentialConfigured.value = null;
    credentialError.value = null;
    try {
      credentialConfigured.value = (await getCredentialStatus()).configured;
    } catch (reason: unknown) {
      credentialError.value = messageFrom(reason);
    } finally {
      credentialLoading.value = false;
    }
  }

  async function saveCredential(secret: string): Promise<void> {
    credentialSaving.value = true;
    credentialError.value = null;
    try {
      credentialConfigured.value = (await saveModelCredential(secret)).configured;
    } catch (reason: unknown) {
      credentialError.value = messageFrom(reason);
      throw reason;
    } finally {
      credentialSaving.value = false;
    }
  }

  async function clearCredential(): Promise<void> {
    credentialSaving.value = true;
    credentialError.value = null;
    try {
      credentialConfigured.value = (await clearModelCredential()).configured;
    } catch (reason: unknown) {
      credentialError.value = messageFrom(reason);
      throw reason;
    } finally {
      credentialSaving.value = false;
    }
  }

  return {
    value,
    loading,
    saving,
    error,
    credentialConfigured,
    credentialLoading,
    credentialSaving,
    credentialError,
    load,
    save,
    loadCredentialStatus,
    saveCredential,
    clearCredential,
  };
});
