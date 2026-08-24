import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import {
  getCredentialStatus,
  getSettings,
  saveModelCredential,
  updateSettings,
  type AppSettings,
} from "../api/settings";
import SettingsView from "./SettingsView.vue";

vi.mock("../api/settings", () => ({
  getSettings: vi.fn(),
  getCredentialStatus: vi.fn(),
  saveModelCredential: vi.fn(),
  clearModelCredential: vi.fn(),
  updateSettings: vi.fn(),
}));

const localSettings: AppSettings = {
  theme: "light",
  model_mode: "local",
  model_provider: "ollama",
  model_name: null,
  base_url: "http://127.0.0.1:11434",
  cloud_data_consent: false,
  updated_at: "2026-08-09T03:00:00Z",
};

describe("SettingsView", () => {
  it("explains local and explicitly confirmed cloud analysis boundaries", async () => {
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    vi.mocked(getCredentialStatus).mockResolvedValue({ configured: false });
    const wrapper = mount(SettingsView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("只有用户主动发起需求分析时才会连接已配置的模型服务");
    expect(wrapper.text()).toContain("API Key 不会保存到 SQLite");
  });

  it("revokes saved cloud consent when the model or endpoint is edited", async () => {
    vi.mocked(getSettings).mockResolvedValue({
      ...localSettings,
      model_mode: "cloud",
      model_provider: "openai_compatible",
      model_name: "qa-model",
      base_url: "https://models.example.com/v1",
      cloud_data_consent: true,
    });
    vi.mocked(getCredentialStatus).mockResolvedValue({ configured: true });
    const wrapper = mount(SettingsView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    expect(
      (wrapper.get('[data-testid="cloud-data-consent"] input').element as HTMLInputElement)
        .checked,
    ).toBe(true);
    await wrapper.get('[data-testid="model-name"]').setValue("qa-model-v2");
    await flushPromises();

    expect(
      (wrapper.get('[data-testid="cloud-data-consent"] input').element as HTMLInputElement)
        .checked,
    ).toBe(false);
    expect(wrapper.get('[data-testid="save-settings"]').attributes("disabled")).toBeDefined();

    await wrapper.get('[data-testid="cloud-data-consent"] input').setValue(true);
    await wrapper.get('[data-testid="model-base-url"]').setValue("https://new.example.com/v1");
    await flushPromises();
    expect(
      (wrapper.get('[data-testid="cloud-data-consent"] input').element as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it("requires cloud consent before saving cloud metadata", async () => {
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    vi.mocked(getCredentialStatus).mockResolvedValue({ configured: false });
    const cloudSettings: AppSettings = {
      ...localSettings,
      model_mode: "cloud",
      model_provider: "openai_compatible",
      model_name: "qa-model",
      base_url: "https://models.example.com/v1",
      cloud_data_consent: true,
    };
    vi.mocked(updateSettings).mockResolvedValue(cloudSettings);
    const wrapper = mount(SettingsView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="model-mode-cloud"]').trigger("click");
    const modelInput = wrapper.get('[data-testid="model-name"]');
    const urlInput = wrapper.get('[data-testid="model-base-url"]');
    await modelInput.setValue("qa-model");
    await urlInput.setValue("https://models.example.com/v1");

    expect(wrapper.get('[data-testid="save-settings"]').attributes("disabled")).toBeDefined();

    await wrapper.get('[data-testid="cloud-data-consent"] input').setValue(true);
    await flushPromises();
    await wrapper.get('[data-testid="save-settings"]').trigger("click");
    await flushPromises();

    expect(updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        model_mode: "cloud",
        model_provider: "openai_compatible",
        cloud_data_consent: true,
      }),
    );
    expect(wrapper.text()).toContain("设置已保存");
  });

  it("clears the credential input immediately after secure storage", async () => {
    vi.mocked(getSettings).mockResolvedValue(localSettings);
    vi.mocked(getCredentialStatus).mockResolvedValue({ configured: false });
    vi.mocked(saveModelCredential).mockResolvedValue({ configured: true });
    const wrapper = mount(SettingsView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="model-mode-cloud"]').trigger("click");
    const credentialInput = wrapper.get('[data-testid="model-api-key"]');
    await credentialInput.setValue("test-credential-value");
    await wrapper.get('[data-testid="save-model-credential"]').trigger("click");
    await flushPromises();

    expect(saveModelCredential).toHaveBeenCalledWith("test-credential-value");
    expect((credentialInput.element as HTMLInputElement).value).toBe("");
    expect(wrapper.text()).toContain("凭据已安全保存");
  });
});
