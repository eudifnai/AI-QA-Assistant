import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { fetchHealth } from "../api/health";
import { selectWorkspaceDirectory } from "../api/backend-connection";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  openWorkspace,
  renameWorkspace,
} from "../api/workspaces";
import WorkspaceView from "./WorkspaceView.vue";

vi.mock("../api/health", () => ({ fetchHealth: vi.fn() }));
vi.mock("../api/backend-connection", () => ({ selectWorkspaceDirectory: vi.fn() }));
vi.mock("../api/workspaces", () => ({
  createWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
  openWorkspace: vi.fn(),
  renameWorkspace: vi.fn(),
}));

describe("WorkspaceView", () => {
  it("fills the workspace path from the native directory picker", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    vi.mocked(listWorkspaces).mockResolvedValue([]);
    vi.mocked(selectWorkspaceDirectory).mockResolvedValue("C:\\qa\\selected");
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="select-workspace-directory"]').trigger("click");
    await flushPromises();

    const inputs = wrapper.findAll("input");
    expect(inputs[1]?.element.value).toBe("C:\\qa\\selected");
  });

  it("creates a workspace from the local path form", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    vi.mocked(listWorkspaces).mockResolvedValue([]);
    vi.mocked(createWorkspace).mockResolvedValue({
      id: "workspace-1",
      name: "支付项目",
      path: "C:\\qa\\payment",
      created_at: "2026-08-04T01:00:00Z",
      last_opened_at: "2026-08-04T01:00:00Z",
    });
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    const inputs = wrapper.findAll("input");
    const nameInput = inputs[0];
    const pathInput = inputs[1];
    if (nameInput === undefined || pathInput === undefined) {
      throw new Error("workspace form inputs are missing");
    }
    await nameInput.setValue("支付项目");
    await pathInput.setValue("C:\\qa\\payment");
    await wrapper.get('[data-testid="create-workspace"]').trigger("click");
    await flushPromises();

    expect(createWorkspace).toHaveBeenCalledWith({
      name: "支付项目",
      path: "C:\\qa\\payment",
    });
    expect(wrapper.text()).toContain("当前工作空间：支付项目");
  });

  it("shows a recoverable list error", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    vi.mocked(listWorkspaces).mockRejectedValue(new Error("无法读取工作空间。"));
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("无法读取工作空间。");
    expect(wrapper.text()).toContain("重新加载");
    expect(openWorkspace).not.toHaveBeenCalled();
  });

  it("renames a workspace from the recent list", async () => {
    const workspace = {
      id: "workspace-1",
      name: "旧名称",
      path: "C:\\qa\\payment",
      created_at: "2026-08-04T01:00:00Z",
      last_opened_at: "2026-08-04T02:00:00Z",
    };
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    vi.mocked(listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(renameWorkspace).mockResolvedValue({ ...workspace, name: "新名称" });
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="rename-workspace-workspace-1"]').trigger("click");
    await wrapper.get('[data-testid="rename-input-workspace-1"]').setValue("新名称");
    await wrapper.get('[data-testid="save-rename-workspace-1"]').trigger("click");
    await flushPromises();

    expect(renameWorkspace).toHaveBeenCalledWith("workspace-1", "新名称");
    expect(wrapper.text()).toContain("新名称");
  });

  it("requires confirmation and explains that local files are preserved", async () => {
    const workspace = {
      id: "workspace-1",
      name: "支付项目",
      path: "C:\\qa\\payment",
      created_at: "2026-08-04T01:00:00Z",
      last_opened_at: "2026-08-04T02:00:00Z",
    };
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    vi.mocked(listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(deleteWorkspace).mockResolvedValue(workspace);
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [createPinia(), ElementPlus] },
    });
    await flushPromises();

    await wrapper.get('[data-testid="delete-workspace-workspace-1"]').trigger("click");

    expect(wrapper.text()).toContain("只删除助手中的记录，不会删除本地目录或文件");
    expect(deleteWorkspace).not.toHaveBeenCalled();

    await wrapper.get('[data-testid="confirm-delete-workspace-1"]').trigger("click");
    await flushPromises();

    expect(deleteWorkspace).toHaveBeenCalledWith("workspace-1");
    expect(wrapper.text()).not.toContain("支付项目");
  });
});
