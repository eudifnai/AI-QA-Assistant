import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  openWorkspace,
  renameWorkspace,
} from "../api/workspaces";
import type { Workspace } from "../api/workspaces";
import { useWorkspaceStore } from "./workspaces";

vi.mock("../api/workspaces", () => ({
  createWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
  openWorkspace: vi.fn(),
  renameWorkspace: vi.fn(),
}));

const workspace: Workspace = {
  id: "workspace-1",
  name: "支付项目",
  path: "C:\\qa\\payment",
  created_at: "2026-08-04T01:00:00Z",
  last_opened_at: "2026-08-04T02:00:00Z",
};

describe("workspace store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(createWorkspace).mockReset();
    vi.mocked(deleteWorkspace).mockReset();
    vi.mocked(listWorkspaces).mockReset();
    vi.mocked(openWorkspace).mockReset();
    vi.mocked(renameWorkspace).mockReset();
  });

  it("loads recent workspaces", async () => {
    vi.mocked(listWorkspaces).mockResolvedValue([workspace]);
    const store = useWorkspaceStore();

    await store.refresh();

    expect(store.items).toEqual([workspace]);
    expect(store.error).toBeNull();
  });

  it("creates and selects a workspace", async () => {
    vi.mocked(createWorkspace).mockResolvedValue(workspace);
    const store = useWorkspaceStore();

    await store.create("支付项目", "C:\\qa\\payment");

    expect(createWorkspace).toHaveBeenCalledWith({
      name: "支付项目",
      path: "C:\\qa\\payment",
    });
    expect(store.items).toEqual([workspace]);
    expect(store.activeWorkspace).toEqual(workspace);
  });

  it("opens an existing workspace and moves it to the front", async () => {
    const older = { ...workspace, id: "workspace-2", name: "旧项目" };
    vi.mocked(listWorkspaces).mockResolvedValue([older, workspace]);
    vi.mocked(openWorkspace).mockResolvedValue(workspace);
    const store = useWorkspaceStore();
    await store.refresh();

    await store.open(workspace.id);

    expect(store.items.map((item) => item.id)).toEqual([workspace.id, older.id]);
    expect(store.activeWorkspace?.id).toBe(workspace.id);
  });

  it("renames a workspace without changing recent order", async () => {
    const older = { ...workspace, id: "workspace-2", name: "旧项目" };
    const renamed = { ...workspace, name: "支付回归" };
    vi.mocked(listWorkspaces).mockResolvedValue([workspace, older]);
    vi.mocked(renameWorkspace).mockResolvedValue(renamed);
    const store = useWorkspaceStore();
    await store.refresh();

    await store.rename(workspace.id, "支付回归");

    expect(renameWorkspace).toHaveBeenCalledWith(workspace.id, "支付回归");
    expect(store.items).toEqual([renamed, older]);
  });

  it("deletes a record and clears the active workspace", async () => {
    vi.mocked(createWorkspace).mockResolvedValue(workspace);
    vi.mocked(deleteWorkspace).mockResolvedValue(workspace);
    const store = useWorkspaceStore();
    await store.create(workspace.name, workspace.path);

    await store.remove(workspace.id);

    expect(deleteWorkspace).toHaveBeenCalledWith(workspace.id);
    expect(store.items).toEqual([]);
    expect(store.activeWorkspace).toBeNull();
  });
});
