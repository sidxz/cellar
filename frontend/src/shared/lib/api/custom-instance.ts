// Custom fetch instance for orval-generated API client.
// Base URL set at runtime via setApiBaseUrl() from AppConfig.
// Auth tokens injected from the shared Sentinel SDK singleton.

import { getSentinelClient } from "@/shared/lib/auth/config";

let _baseUrl = "http://localhost:8000";

/**
 * Versioned API path prefix shared by every hand-written hook/component that
 * builds a request URL by hand. Compose URLs as `` `${API_V1}/...` `` instead
 * of hard-coding the `/api/v1` literal at each call site, so a future version
 * bump is a single edit. (orval-generated clients embed the prefix themselves.)
 */
export const API_V1 = "/api/v1";

/** Called by AuthProvider after fetching runtime AppConfig. */
export function setApiBaseUrl(url: string) {
  _baseUrl = url;
}

/** Get the current base URL for direct fetch calls (e.g., file upload). */
export function getApiBaseUrl() {
  return _baseUrl;
}

/**
 * Sentinel auth headers for direct `fetch` calls that bypass `customInstance`
 * (file uploads, binary downloads). Returns `{}` on the server or when the
 * client isn't authenticated. Centralized so the same `isAuthenticated` guard
 * is applied everywhere instead of being re-derived per call site.
 */
export function getAuthHeaders(): Record<string, string> {
  const client = typeof window !== "undefined" ? getSentinelClient() : null;
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
    let detail: string | undefined;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail
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
    throw new Error(
      detail ? `API error: ${response.status} — ${detail}` : `API error: ${response.status}`,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
};
