import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { createBackup, getDiagnostics, listBackups } from "../api/maintenance";
import MaintenanceView from "./MaintenanceView.vue";

vi.mock("../api/maintenance", () => ({
  createBackup: vi.fn(),
  getDiagnostics: vi.fn(),
  listBackups: vi.fn(),
}));

const diagnostics = {
  app_version: "0.1.0",
  python_version: "3.12.11",
  platform: "Windows-11",
  api_host: "127.0.0.1",
  database_path: "C:\\data\\app.db",
  backup_directory: "C:\\data\\backups",
  database_size_bytes: 2048,
  database_integrity: "ok" as const,
  database_revision: "20260809_0003",
  workspace_count: 2,
  backup_count: 0,
};
const backup = {
  file_name: "app.db",
  path: "C:\\data\\backups\\app.db",
  created_at: "2026-08-10T02:00:00Z",
  size_bytes: 1024,
};

describe("MaintenanceView", () => {
  it("explains backup scope and creates a database backup", async () => {
    vi.mocked(getDiagnostics).mockResolvedValue(diagnostics);
    vi.mocked(listBackups).mockResolvedValue([]);
    vi.mocked(createBackup).mockResolvedValue(backup);
    const wrapper = mount(MaintenanceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("不包含工作空间原文件或系统凭据");
    expect(wrapper.text()).toContain("20260809_0003");

    await wrapper.get('[data-testid="create-database-backup"]').trigger("click");
    await flushPromises();

    expect(createBackup).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("app.db");
  });
});
