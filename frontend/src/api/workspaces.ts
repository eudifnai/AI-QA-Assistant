import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export interface Workspace {
  id: string;
  name: string;
  path: string;
  created_at: string;
  last_opened_at: string;
}

export interface CreateWorkspaceInput {
  name: string;
  path: string;
}

function isWorkspace(value: unknown): value is Workspace {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<Workspace>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.name === "string" &&
    typeof candidate.path === "string" &&
    typeof candidate.created_at === "string" &&
    typeof candidate.last_opened_at === "string"
  );
}

function validateWorkspace(value: unknown): Workspace {
  if (!isWorkspace(value)) {
    throw new ApiClientError("后端工作空间响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return value;
}

async function workspaceClient(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function listWorkspaces(): Promise<Workspace[]> {
  const client = await workspaceClient();
  const response = await client.get<unknown>("/api/workspaces");
  if (!Array.isArray(response)) {
    throw new ApiClientError("后端工作空间响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return response.map(validateWorkspace);
}

export async function createWorkspace(input: CreateWorkspaceInput): Promise<Workspace> {
  const client = await workspaceClient();
  return validateWorkspace(await client.post<unknown>("/api/workspaces", input));
}

export async function openWorkspace(workspaceId: string): Promise<Workspace> {
  const client = await workspaceClient();
  return validateWorkspace(
    await client.post<unknown>(`/api/workspaces/${encodeURIComponent(workspaceId)}/open`),
  );
}

export async function renameWorkspace(workspaceId: string, name: string): Promise<Workspace> {
  const client = await workspaceClient();
  return validateWorkspace(
    await client.patch<unknown>(`/api/workspaces/${encodeURIComponent(workspaceId)}`, { name }),
  );
}

export async function deleteWorkspace(workspaceId: string): Promise<Workspace> {
  const client = await workspaceClient();
  return validateWorkspace(
    await client.delete<unknown>(`/api/workspaces/${encodeURIComponent(workspaceId)}`),
  );
}
