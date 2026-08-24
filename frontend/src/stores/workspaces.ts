import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  openWorkspace,
  renameWorkspace,
  type Workspace,
} from "../api/workspaces";

export const useWorkspaceStore = defineStore("workspaces", () => {
  const items = ref<Workspace[]>([]);
  const activeWorkspaceId = ref<string | null>(null);
  const loading = ref(false);
  const creating = ref(false);
  const openingId = ref<string | null>(null);
  const renamingId = ref<string | null>(null);
  const deletingId = ref<string | null>(null);
  const error = ref<string | null>(null);

  const activeWorkspace = computed(
    () => items.value.find((item) => item.id === activeWorkspaceId.value) ?? null,
  );

  function messageFrom(reason: unknown): string {
    return reason instanceof Error ? reason.message : "工作空间操作失败。";
  }

  function moveToFront(workspace: Workspace): void {
    items.value = [workspace, ...items.value.filter((item) => item.id !== workspace.id)];
  }

  async function refresh(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await listWorkspaces();
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
    } finally {
      loading.value = false;
    }
  }

  async function create(name: string, path: string): Promise<void> {
    creating.value = true;
    error.value = null;
    try {
      const workspace = await createWorkspace({ name, path });
      moveToFront(workspace);
      activeWorkspaceId.value = workspace.id;
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      creating.value = false;
    }
  }

  async function open(workspaceId: string): Promise<void> {
    openingId.value = workspaceId;
    error.value = null;
    try {
      const workspace = await openWorkspace(workspaceId);
      moveToFront(workspace);
      activeWorkspaceId.value = workspace.id;
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      openingId.value = null;
    }
  }

  async function rename(workspaceId: string, name: string): Promise<void> {
    renamingId.value = workspaceId;
    error.value = null;
    try {
      const workspace = await renameWorkspace(workspaceId, name);
      items.value = items.value.map((item) => (item.id === workspace.id ? workspace : item));
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      renamingId.value = null;
    }
  }

  async function remove(workspaceId: string): Promise<void> {
    deletingId.value = workspaceId;
    error.value = null;
    try {
      await deleteWorkspace(workspaceId);
      items.value = items.value.filter((item) => item.id !== workspaceId);
      if (activeWorkspaceId.value === workspaceId) {
        activeWorkspaceId.value = null;
      }
    } catch (reason: unknown) {
      error.value = messageFrom(reason);
      throw reason;
    } finally {
      deletingId.value = null;
    }
  }

  return {
    items,
    activeWorkspaceId,
    activeWorkspace,
    loading,
    creating,
    openingId,
    renamingId,
    deletingId,
    error,
    refresh,
    create,
    open,
    rename,
    remove,
  };
});
