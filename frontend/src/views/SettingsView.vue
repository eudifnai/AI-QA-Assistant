<script setup lang="ts">
import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElForm,
  ElFormItem,
  ElInput,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElOption,
  ElTag,
} from "element-plus";
import { storeToRefs } from "pinia";
import { computed, onMounted, reactive, ref } from "vue";

import type { ModelMode, SettingsUpdateInput } from "../api/settings";
import { useSettingsStore } from "../stores/settings";

const settingsStore = useSettingsStore();
const {
  value,
  loading,
  saving,
  error,
  credentialConfigured,
  credentialLoading,
  credentialSaving,
  credentialError,
} = storeToRefs(settingsStore);
const saved = ref(false);
const modelCredential = ref("");
const credentialSaved = ref(false);
const confirmingCredentialClear = ref(false);
const form = reactive<SettingsUpdateInput>({
  theme: "light",
  model_mode: "local",
  model_provider: "ollama",
  model_name: null,
  base_url: "http://127.0.0.1:11434",
  cloud_data_consent: false,
});

const canSave = computed(
  () =>
    form.base_url.trim().length > 0 &&
    (form.model_mode === "local" || form.cloud_data_consent),
);

function copyFromStore(): void {
  if (value.value === null) {
    return;
  }
  Object.assign(form, {
    theme: value.value.theme,
    model_mode: value.value.model_mode,
    model_provider: value.value.model_provider,
    model_name: value.value.model_name,
    base_url: value.value.base_url,
    cloud_data_consent: value.value.cloud_data_consent,
  });
}

function selectMode(mode: ModelMode): void {
  form.model_mode = mode;
  saved.value = false;
  if (mode === "local") {
    form.model_provider = "ollama";
    form.base_url = "http://127.0.0.1:11434";
    form.cloud_data_consent = false;
  } else {
    form.model_provider = "openai_compatible";
    form.base_url = "https://";
    form.cloud_data_consent = false;
  }
}

function resetCloudConsent(): void {
  if (form.model_mode === "cloud") {
    form.cloud_data_consent = false;
    saved.value = false;
  }
}

async function saveSettings(): Promise<void> {
  if (!canSave.value) {
    return;
  }
  saved.value = false;
  try {
    await settingsStore.save({
      ...form,
      model_name: form.model_name?.trim() || null,
      base_url: form.base_url.trim(),
    });
    copyFromStore();
    saved.value = true;
  } catch {
    // The store exposes the safe API message in its recoverable error state.
  }
}

async function saveCredential(): Promise<void> {
  if (modelCredential.value.length < 8) {
    return;
  }
  credentialSaved.value = false;
  try {
    await settingsStore.saveCredential(modelCredential.value);
    credentialSaved.value = true;
  } catch {
    // The store exposes the safe credential error without echoing the secret.
  } finally {
    modelCredential.value = "";
  }
}

async function clearCredential(): Promise<void> {
  try {
    await settingsStore.clearCredential();
    credentialSaved.value = false;
    confirmingCredentialClear.value = false;
  } catch {
    // Keep the confirmation visible and expose the safe store error.
  }
}

onMounted(async () => {
  if (value.value === null) {
    await settingsStore.load();
  }
  copyFromStore();
  await settingsStore.loadCredentialStatus();
});
</script>

<template>
  <main class="settings-page">
    <div class="settings-heading">
      <div>
        <p class="eyebrow">LOCAL-FIRST SETTINGS</p>
        <h1>用户设置</h1>
        <p>配置仅保存在本机；只有用户主动发起需求分析时才会连接已配置的模型服务。</p>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert
      v-if="saved"
      title="设置已保存"
      type="success"
      :closable="false"
      show-icon
    />

    <el-form v-loading="loading" label-position="top" @submit.prevent="saveSettings">
      <el-card shadow="never">
        <template #header><h2>界面</h2></template>
        <el-form-item label="主题">
          <el-select v-model="form.theme" aria-label="界面主题">
            <el-option label="浅色" value="light" />
            <el-option label="深色" value="dark" />
          </el-select>
        </el-form-item>
      </el-card>

      <el-card class="model-card" shadow="never">
        <template #header>
          <div>
            <h2>模型配置</h2>
            <p>API Key 不会保存到 SQLite；云端分析仅在逐次确认后外发所选文档片段。</p>
          </div>
        </template>

        <el-form-item label="运行模式">
          <el-radio-group :model-value="form.model_mode">
            <el-radio-button
              data-testid="model-mode-local"
              value="local"
              @click="selectMode('local')"
            >
              本地 Ollama
            </el-radio-button>
            <el-radio-button
              data-testid="model-mode-cloud"
              value="cloud"
              @click="selectMode('cloud')"
            >
              云端 OpenAI-compatible
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="Provider">
          <el-input :model-value="form.model_provider" disabled />
        </el-form-item>
        <el-form-item label="模型名称（可选）">
          <el-input
            v-model="form.model_name"
            data-testid="model-name"
            maxlength="120"
            placeholder="例如：qwen3:8b"
            @input="resetCloudConsent"
          />
        </el-form-item>
        <el-form-item label="服务地址">
          <el-input
            v-model="form.base_url"
            data-testid="model-base-url"
            maxlength="2048"
            @input="resetCloudConsent"
          />
        </el-form-item>

        <el-alert
          v-if="form.model_mode === 'local'"
          title="本地模式只接受 localhost、127.0.0.0/8 或 ::1 回环地址，不会自动回退到云端。"
          type="info"
          :closable="false"
          show-icon
        />
        <el-checkbox
          v-else
          v-model="form.cloud_data_consent"
          data-testid="cloud-data-consent"
          class="cloud-consent"
        >
          我已了解明确选定的数据可能发送到该 Provider；每次外发还必须在分析页逐次确认。
        </el-checkbox>

        <section v-if="form.model_mode === 'cloud'" class="credential-section">
          <div class="credential-heading">
            <div>
              <h3>系统凭据库</h3>
              <p>API Key 直接写入操作系统凭据库；页面、响应和 SQLite 都不会保存或回显密钥。</p>
            </div>
            <el-tag v-if="credentialLoading" type="info">正在检查</el-tag>
            <el-tag v-else :type="credentialConfigured ? 'success' : 'info'">
              {{ credentialConfigured ? "已配置" : "未配置" }}
            </el-tag>
          </div>
          <el-alert
            v-if="credentialError"
            :title="credentialError"
            type="error"
            :closable="false"
            show-icon
          />
          <el-alert
            v-if="credentialSaved"
            title="凭据已安全保存"
            type="success"
            :closable="false"
            show-icon
          />
          <el-input
            v-model="modelCredential"
            data-testid="model-api-key"
            type="password"
            autocomplete="new-password"
            show-password
            maxlength="8192"
            placeholder="输入新的 API Key；保存后输入框立即清空"
          />
          <div class="credential-actions">
            <el-button
              data-testid="save-model-credential"
              :loading="credentialSaving"
              :disabled="modelCredential.length < 8"
              @click="saveCredential"
            >
              保存到系统凭据库
            </el-button>
            <template v-if="credentialConfigured">
              <el-button
                v-if="!confirmingCredentialClear"
                type="danger"
                plain
                @click="confirmingCredentialClear = true"
              >
                清除凭据
              </el-button>
              <template v-else>
                <el-button
                  data-testid="confirm-clear-model-credential"
                  type="danger"
                  :loading="credentialSaving"
                  @click="clearCredential"
                >
                  确认清除
                </el-button>
                <el-button @click="confirmingCredentialClear = false">取消</el-button>
              </template>
            </template>
          </div>
        </section>
      </el-card>

      <el-button
        data-testid="save-settings"
        type="primary"
        :loading="saving"
        :disabled="!canSave"
        @click="saveSettings"
      >
        保存设置
      </el-button>
    </el-form>
  </main>
</template>

<style scoped>
.settings-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 36px clamp(20px, 5vw, 72px) 56px;
  color: var(--app-text);
}

.settings-heading,
.model-card {
  margin-bottom: 20px;
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

h2 {
  margin-bottom: 0;
  font-size: 18px;
}

.model-card p {
  margin: 6px 0 0;
  color: var(--app-muted);
}

.cloud-consent {
  height: auto;
  margin: 18px 0;
  white-space: normal;
}

.credential-section {
  display: grid;
  gap: 14px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--app-border);
}

.credential-heading,
.credential-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.credential-heading h3,
.credential-heading p {
  margin-bottom: 0;
}

.credential-heading h3 {
  font-size: 16px;
}

.credential-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.credential-actions .el-button + .el-button {
  margin-left: 0;
}
</style>
