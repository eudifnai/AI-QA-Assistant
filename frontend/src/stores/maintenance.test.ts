import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createBackup,
  getDiagnostics,
  listBackups,
  type BackupInfo,
  type DiagnosticsReport,
} from "../api/maintenance";
import { useMaintenanceStore } from "./maintenance";

vi.mock("../api/maintenance", () => ({
  createBackup: vi.fn(),
  getDiagnostics: vi.fn(),
  listBackups: vi.fn(),
}));

const backup: BackupInfo = {
  file_name: "app.db",
  path: "C:\\data\\backups\\app.db",
  created_at: "2026-08-10T02:00:00Z",
  size_bytes: 1024,
};
const diagnostics: DiagnosticsReport = {
  app_version: "0.1.0",
  python_version: "3.12.11",
  platform: "Windows-11",
  api_host: "127.0.0.1",
  database_path: "C:\\data\\app.db",
  backup_directory: "C:\\data\\backups",
  database_size_bytes: 2048,
  database_integrity: "ok",
  database_revision: "20260809_0003",
  workspace_count: 2,
  backup_count: 1,
};

describe("maintenance store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(getDiagnostics).mockReset();
    vi.mocked(listBackups).mockReset();
    vi.mocked(createBackup).mockReset();
  });

  it("loads diagnostics and backups together", async () => {
    vi.mocked(getDiagnostics).mockResolvedValue(diagnostics);
    vi.mocked(listBackups).mockResolvedValue([backup]);
    const store = useMaintenanceStore();

    await store.refresh();

    expect(store.diagnostics).toEqual(diagnostics);
    expect(store.backups).toEqual([backup]);
  });

  it("creates a backup and refreshes diagnostics", async () => {
    vi.mocked(createBackup).mockResolvedValue(backup);
    vi.mocked(getDiagnostics).mockResolvedValue(diagnostics);
    const store = useMaintenanceStore();

    await store.create();

    expect(store.backups).toEqual([backup]);
    expect(store.diagnostics).toEqual(diagnostics);
  });
});
