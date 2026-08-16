// Custom fetch instance for orval-generated API client.
// Base URL set at runtime via setApiBaseUrl() from AppConfig.
// Auth tokens injected from the shared Duar SDK singleton.

import { getDuarClient } from "@/shared/lib/auth/config";

let _baseUrl = "http://localhost:8000";

/**
 * Versioned API path prefix shared by every hand-written hook/component that
 * builds a request URL by hand. Compose URLs as `` `${API_V1}/...` `` instead
 * of hard-coding the `/api/v1` literal at each call site, so a future version
 * bump is a single edit. (orval-generated clients embed the prefix themselves.)
 */
export const API_V1 = "/api/v1";

/**
 * Error thrown by {@link customInstance} for any non-2xx response.
 *
 * Extends the native `Error` so existing callers that only read `.message`
 * (or check `instanceof Error`) keep working unchanged — the human-readable
 * `API error: <status> — <detail>` message is preserved. Callers that need to
 * branch on the server's structured payload (e.g. the admin/cascade delete
 * blocker contract `{error, message, blockers}`) can narrow via
 * `instanceof ApiError` and inspect `status` + the parsed `body`.
 */
export class ApiError extends Error {
  /** HTTP status code of the failed response. */
  readonly status: number;
  /**
   * Parsed JSON response body, or `undefined` when the body was empty or not
   * JSON. The shape is server-defined; narrow it before use.
   */
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** Called by AuthProvider after fetching runtime AppConfig. */
export function setApiBaseUrl(url: string) {
  _baseUrl = url;
}

/** Get the current base URL for direct fetch calls (e.g., file upload). */
export function getApiBaseUrl() {
  return _baseUrl;
}

/**
 * Duar auth headers for direct `fetch` calls that bypass `customInstance`
 * (file uploads, binary downloads). Returns `{}` on the server or when the
 * client isn't authenticated. Centralized so the same `isAuthenticated` guard
 * is applied everywhere instead of being re-derived per call site.
 */
export function getAuthHeaders(): Record<string, string> {
  const client = typeof window !== "undefined" ? getDuarClient() : null;
  return client?.isAuthenticated ? client.getHeaders() : {};
}

export const customInstance = async <T>({
  url,
  method,
  params,
  data,
  headers,
  signal,
}: {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  // biome-ignore lint/suspicious/noExplicitAny: orval generates params with mixed primitive types
  params?: Record<string, any>;
  data?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}): Promise<T> => {
  // Build query string. Arrays are emitted as repeated keys (`k=a&k=b`),
  // matching FastAPI's `list[T] = Query(...)` expectation. Scalars are
  // stringified; null/undefined entries (and null/undefined array items)
  // are skipped.
  const searchParams = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v == null) continue;
      if (Array.isArray(v)) {
        for (const item of v) {
          if (item == null) continue;
          searchParams.append(k, String(item));
        }
      } else {
        searchParams.append(k, String(v));
      }
    }
  }
  const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

  const authHeaders = getAuthHeaders();

  const isFormData = typeof FormData !== "undefined" && data instanceof FormData;

  const fetchHeaders: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...authHeaders,
    ...headers,
  };

  const response = await fetch(`${_baseUrl}${url}${queryString}`, {
    method,
    headers: fetchHeaders,
    signal,
    ...(data
      ? { body: isFormData ? (data as FormData) : JSON.stringify(data) }
      : {}),
  });

  if (!response.ok) {
    // Surface the response body's `detail` so chemists see what the
    // server actually rejected, not just a status code. FastAPI emits
    // two shapes: custom 422s from result_to_response (`{detail: "..."}`)
    // and Pydantic request-validation 422s (`{detail: [{loc, msg, ...}]}`).
    // The parsed body is retained on the thrown ApiError so callers that need
    // the structured domain payload (e.g. the delete-blocker `{error,
    // message, blockers}` contract, which lives at the top level — not under
    // `detail`) can read it without re-fetching.
    let body: unknown;
    let detail: string | undefined;
    try {
      body = await response.json();
      const parsed = body as { detail?: unknown } | null;
      if (typeof parsed?.detail === "string") {
        detail = parsed.detail;
      } else if (Array.isArray(parsed?.detail)) {
        detail = parsed.detail
          .map((d: { loc?: unknown; msg?: unknown }) => {
            const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
            const msg = typeof d.msg === "string" ? d.msg : JSON.stringify(d);
            return loc ? `${loc}: ${msg}` : msg;
          })
          .join("; ");
      }
    } catch {
      // body not JSON or already consumed — fall through with no detail
    }
    throw new ApiError(
      detail ? `API error: ${response.status} — ${detail}` : `API error: ${response.status}`,
      response.status,
      body,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
};
