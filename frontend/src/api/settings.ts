import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export type Theme = "light" | "dark";
export type ModelMode = "local" | "cloud";
export type ModelProvider = "ollama" | "openai_compatible";

export interface SettingsUpdateInput {
  theme: Theme;
  model_mode: ModelMode;
  model_provider: ModelProvider;
  model_name: string | null;
  base_url: string;
  cloud_data_consent: boolean;
}

export interface AppSettings extends SettingsUpdateInput {
  updated_at: string;
}

export interface CredentialStatus {
  configured: boolean;
}

function isSettings(value: unknown): value is AppSettings {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<AppSettings>;
  return (
    (candidate.theme === "light" || candidate.theme === "dark") &&
    (candidate.model_mode === "local" || candidate.model_mode === "cloud") &&
    (candidate.model_provider === "ollama" ||
      candidate.model_provider === "openai_compatible") &&
    (candidate.model_name === null || typeof candidate.model_name === "string") &&
    typeof candidate.base_url === "string" &&
    typeof candidate.cloud_data_consent === "boolean" &&
    typeof candidate.updated_at === "string"
  );
}

function validateSettings(value: unknown): AppSettings {
  if (!isSettings(value)) {
    throw new ApiClientError("后端设置响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value;
}

function validateCredentialStatus(value: unknown): CredentialStatus {
  if (
    typeof value !== "object" ||
    value === null ||
    typeof (value as Partial<CredentialStatus>).configured !== "boolean"
  ) {
    throw new ApiClientError("后端凭据状态响应格式不正确。", { code: "INVALID_RESPONSE" });
  }
  return value as CredentialStatus;
}

async function settingsClient(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function getSettings(): Promise<AppSettings> {
  const client = await settingsClient();
  return validateSettings(await client.get<unknown>("/api/settings"));
}

export async function updateSettings(input: SettingsUpdateInput): Promise<AppSettings> {
  const client = await settingsClient();
  return validateSettings(await client.put<unknown>("/api/settings", input));
}

export async function getCredentialStatus(): Promise<CredentialStatus> {
  const client = await settingsClient();
  return validateCredentialStatus(await client.get<unknown>("/api/settings/model-credential"));
}

export async function saveModelCredential(apiKey: string): Promise<CredentialStatus> {
  const client = await settingsClient();
  return validateCredentialStatus(
    await client.put<unknown>("/api/settings/model-credential", { api_key: apiKey }),
  );
}

export async function clearModelCredential(): Promise<CredentialStatus> {
  const client = await settingsClient();
  return validateCredentialStatus(
    await client.delete<unknown>("/api/settings/model-credential"),
  );
}
