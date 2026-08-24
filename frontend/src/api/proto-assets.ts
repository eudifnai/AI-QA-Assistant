import { resolveBackendConnection } from "./backend-connection";
import { ApiClient, ApiClientError } from "./client";

export interface ProtoField {
  name: string;
  number: number;
  type: string;
  label: string;
  type_name: string | null;
}

export interface ProtoMessage {
  name: string;
  full_name: string;
  fields: ProtoField[];
}

export interface ProtoEnum {
  name: string;
  full_name: string;
  values: Array<{ name: string; number: number }>;
}

export interface ProtoMethod {
  name: string;
  input_type: string;
  output_type: string;
  client_streaming: boolean;
  server_streaming: boolean;
}

export interface ProtoService {
  name: string;
  full_name: string;
  methods: ProtoMethod[];
}

export interface ProtoAsset {
  id: string;
  workspace_id: string;
  name: string;
  relative_path: string;
  sha256: string;
  size_bytes: number;
  packages: string[];
  messages: ProtoMessage[];
  enums: ProtoEnum[];
  services: ProtoService[];
  created_at: string;
  updated_at: string;
}

export interface ProtoEncodeInput {
  expected_sha256: string;
  message_type: string;
  payload: Record<string, unknown>;
}

export interface ProtoEncodeResult {
  data_base64: string;
  size_bytes: number;
}

export interface ProtoDecodeInput {
  expected_sha256: string;
  message_type: string;
  data_base64: string;
}

export interface ProtoDecodeResult {
  payload: Record<string, unknown>;
  size_bytes: number;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isProtoField(value: unknown): value is ProtoField {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<ProtoField>;
  return (
    typeof item.name === "string" &&
    Number.isInteger(item.number) &&
    typeof item.type === "string" &&
    typeof item.label === "string" &&
    (item.type_name === null || typeof item.type_name === "string")
  );
}

function isProtoMessage(value: unknown): value is ProtoMessage {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<ProtoMessage>;
  return (
    typeof item.name === "string" &&
    typeof item.full_name === "string" &&
    Array.isArray(item.fields) &&
    item.fields.every(isProtoField)
  );
}

function isProtoEnum(value: unknown): value is ProtoEnum {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<ProtoEnum>;
  return (
    typeof item.name === "string" &&
    typeof item.full_name === "string" &&
    Array.isArray(item.values) &&
    item.values.every(
      (entry) =>
        typeof entry === "object" &&
        entry !== null &&
        typeof entry.name === "string" &&
        Number.isInteger(entry.number),
    )
  );
}

function isProtoService(value: unknown): value is ProtoService {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<ProtoService>;
  return (
    typeof item.name === "string" &&
    typeof item.full_name === "string" &&
    Array.isArray(item.methods) &&
    item.methods.every(
      (method) =>
        typeof method === "object" &&
        method !== null &&
        typeof method.name === "string" &&
        typeof method.input_type === "string" &&
        typeof method.output_type === "string" &&
        typeof method.client_streaming === "boolean" &&
        typeof method.server_streaming === "boolean",
    )
  );
}

function isProtoAsset(value: unknown): value is ProtoAsset {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<ProtoAsset>;
  return (
    typeof item.id === "string" &&
    typeof item.workspace_id === "string" &&
    typeof item.name === "string" &&
    typeof item.relative_path === "string" &&
    typeof item.sha256 === "string" &&
    /^[0-9a-f]{64}$/.test(item.sha256) &&
    Number.isInteger(item.size_bytes) &&
    isStringArray(item.packages) &&
    Array.isArray(item.messages) &&
    item.messages.every(isProtoMessage) &&
    Array.isArray(item.enums) &&
    item.enums.every(isProtoEnum) &&
    Array.isArray(item.services) &&
    item.services.every(isProtoService) &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

function asset(value: unknown): ProtoAsset {
  if (!isProtoAsset(value)) {
    throw new ApiClientError("后端 Proto 资产响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return value;
}

async function client(): Promise<ApiClient> {
  const connection = await resolveBackendConnection();
  return new ApiClient(connection.baseUrl, connection.token);
}

export async function listProtoAssets(workspaceId: string): Promise<ProtoAsset[]> {
  const response = await (await client()).get<unknown>(
    `/api/workspaces/${workspaceId}/proto-assets`,
  );
  if (!Array.isArray(response) || !response.every(isProtoAsset)) {
    throw new ApiClientError("后端 Proto 资产列表响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return response;
}

export async function importProtoAsset(
  workspaceId: string,
  sourcePath: string,
): Promise<ProtoAsset> {
  return asset(
    await (await client()).post<unknown>(`/api/workspaces/${workspaceId}/proto-assets`, {
      source_path: sourcePath,
    }),
  );
}

export async function encodeProtoMessage(
  workspaceId: string,
  assetId: string,
  input: ProtoEncodeInput,
): Promise<ProtoEncodeResult> {
  const response = await (await client()).post<unknown>(
    `/api/workspaces/${workspaceId}/proto-assets/${assetId}/encode`,
    input,
  );
  if (
    typeof response !== "object" ||
    response === null ||
    typeof (response as Partial<ProtoEncodeResult>).data_base64 !== "string" ||
    !Number.isInteger((response as Partial<ProtoEncodeResult>).size_bytes)
  ) {
    throw new ApiClientError("后端 Protobuf 编码响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return response as ProtoEncodeResult;
}

export async function decodeProtoMessage(
  workspaceId: string,
  assetId: string,
  input: ProtoDecodeInput,
): Promise<ProtoDecodeResult> {
  const response = await (await client()).post<unknown>(
    `/api/workspaces/${workspaceId}/proto-assets/${assetId}/decode`,
    input,
  );
  if (
    typeof response !== "object" ||
    response === null ||
    typeof (response as Partial<ProtoDecodeResult>).payload !== "object" ||
    (response as Partial<ProtoDecodeResult>).payload === null ||
    Array.isArray((response as Partial<ProtoDecodeResult>).payload) ||
    !Number.isInteger((response as Partial<ProtoDecodeResult>).size_bytes)
  ) {
    throw new ApiClientError("后端 Protobuf 解码响应格式不正确。", {
      code: "INVALID_RESPONSE",
    });
  }
  return response as ProtoDecodeResult;
}
