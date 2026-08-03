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

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async get<T>(path: string): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: "GET",
        headers: { Accept: "application/json" },
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

