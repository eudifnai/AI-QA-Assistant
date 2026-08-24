import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export interface HealthResponse {
  status: "ok";
  version: string;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<HealthResponse>;
  return candidate.status === "ok" && typeof candidate.version === "string";
}

export async function fetchHealth(): Promise<HealthResponse> {
  const connection = await resolveBackendConnection();
  const apiClient = new ApiClient(connection.baseUrl, connection.token);
  const response = await apiClient.get<unknown>("/health");
  if (!isHealthResponse(response)) {
    throw new ApiClientError("后端健康响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return response;
}
