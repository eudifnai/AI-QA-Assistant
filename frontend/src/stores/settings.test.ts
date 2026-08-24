import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearModelCredential,
  getCredentialStatus,
  getSettings,
  saveModelCredential,
  updateSettings,
  type AppSettings,
} from "../api/settings";
import { useSettingsStore } from "./settings";

vi.mock("../api/settings", () => ({
  getSettings: vi.fn(),
  getCredentialStatus: vi.fn(),
  saveModelCredential: vi.fn(),
  clearModelCredential: vi.fn(),
  updateSettings: vi.fn(),
}));

const settings: AppSettings = {
  theme: "dark",
  model_mode: "local",
  model_provider: "ollama",
  model_name: "qwen3:8b",
  base_url: "http://127.0.0.1:11434",
  cloud_data_consent: false,
  updated_at: "2026-08-09T03:00:00Z",
};

describe("settings store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    document.documentElement.classList.remove("dark");
    vi.mocked(getSettings).mockReset();
    vi.mocked(getCredentialStatus).mockReset();
    vi.mocked(saveModelCredential).mockReset();
    vi.mocked(clearModelCredential).mockReset();
    vi.mocked(updateSettings).mockReset();
  });

  it("loads settings and applies the persisted theme", async () => {
    vi.mocked(getSettings).mockResolvedValue(settings);
    const store = useSettingsStore();

    await store.load();

    expect(store.value).toEqual(settings);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("saves settings and applies the returned theme", async () => {
    const light = { ...settings, theme: "light" as const };
    vi.mocked(updateSettings).mockResolvedValue(light);
    const store = useSettingsStore();

    await store.save(light);

    expect(updateSettings).toHaveBeenCalledWith({
      theme: "light",
      model_mode: "local",
      model_provider: "ollama",
      model_name: "qwen3:8b",
      base_url: "http://127.0.0.1:11434",
      cloud_data_consent: false,
    });
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("reuses an in-flight initial load", async () => {
    let resolveSettings: ((value: AppSettings) => void) | undefined;
    vi.mocked(getSettings).mockReturnValue(
      new Promise((resolve) => {
        resolveSettings = resolve;
      }),
    );
    const store = useSettingsStore();

    const first = store.load();
    const second = store.load();

    expect(getSettings).toHaveBeenCalledTimes(1);
    resolveSettings?.(settings);
    await Promise.all([first, second]);
    expect(store.value).toEqual(settings);
  });

  it("stores and clears only credential status", async () => {
    vi.mocked(saveModelCredential).mockResolvedValue({ configured: true });
    vi.mocked(clearModelCredential).mockResolvedValue({ configured: false });
    const store = useSettingsStore();

    await store.saveCredential("test-credential-value");
    expect(store.credentialConfigured).toBe(true);

    await store.clearCredential();
    expect(store.credentialConfigured).toBe(false);
    expect(saveModelCredential).toHaveBeenCalledWith("test-credential-value");
  });
});
