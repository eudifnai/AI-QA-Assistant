const DEFAULT_TIMEOUT_MS = 5_000;

interface ApiErrorPayload {
  code?: unknown;
  message?: unknown;
  trace_id?: unknown;
}

export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly traceId: string | null;

  constructor(
    message: string,
    options: { code: string; status?: number | null; traceId?: string | null },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.code = options.code;
    this.status = options.status ?? null;
    this.traceId = options.traceId ?? null;
  }
}

function asErrorPayload(value: unknown): ApiErrorPayload | null {
  return typeof value === "object" && value !== null ? (value as ApiErrorPayload) : null;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly token: string | null;

  constructor(baseUrl: string, token: string | null = null) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }

  private async request<T>(
    path: string,
    request: { method: "DELETE" | "GET" | "PATCH" | "POST" | "PUT"; body?: string },
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
      const headers: Record<string, string> = { Accept: "application/json" };
      if (this.token !== null) {
        headers.Authorization = `Bearer ${this.token}`;
      }
      if (request.body !== undefined) {
        headers["Content-Type"] = "application/json";
      }
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: request.method,
        headers,
        body: request.body,
        signal: controller.signal,
      });

      if (!response.ok) {
        let body: unknown = null;
        try {
          body = await response.json();
        } catch {
          // A non-JSON failure is mapped to a generic, non-sensitive message below.
        }
        const payload = asErrorPayload(body);
        throw new ApiClientError(
          typeof payload?.message === "string" ? payload.message : "本地后端请求失败。",
          {
            code: typeof payload?.code === "string" ? payload.code : "HTTP_ERROR",
            status: response.status,
            traceId: typeof payload?.trace_id === "string" ? payload.trace_id : null,
          },
        );
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (error: unknown) {
      if (error instanceof ApiClientError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiClientError("连接本地后端超时。", { code: "REQUEST_TIMEOUT" });
      }
      throw new ApiClientError("无法连接本地后端。", { code: "BACKEND_UNAVAILABLE" });
    } finally {
      window.clearTimeout(timeout);
    }
  }
}
