import { ApiClient, ApiClientError } from "./client";

export interface HealthResponse {
  status: "ok";
  version: string;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765";
const apiClient = new ApiClient(apiBaseUrl);

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<HealthResponse>;
  return candidate.status === "ok" && typeof candidate.version === "string";
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<unknown>("/health");
  if (!isHealthResponse(response)) {
    throw new ApiClientError("后端健康响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return response;
}

