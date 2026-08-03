import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { fetchHealth } from "../api/health";
import HealthView from "./HealthView.vue";

vi.mock("../api/health", () => ({
  fetchHealth: vi.fn(),
}));

describe("HealthView", () => {
  it("renders the backend version after a successful check", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "2.4.6" });

    const wrapper = mount(HealthView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("后端服务正常");
    expect(wrapper.text()).toContain("2.4.6");
  });
});
