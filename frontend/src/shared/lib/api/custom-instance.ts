// Custom fetch instance for orval-generated API client.
// Base URL set at runtime via setApiBaseUrl() from AppConfig.
// Auth tokens injected from the shared Sentinel SDK singleton.

import { getSentinelClient } from "@/shared/lib/auth/config";

let _baseUrl = "http://localhost:8000";

/** Called by AuthProvider after fetching runtime AppConfig. */
export function setApiBaseUrl(url: string) {
  _baseUrl = url;
}

/** Get the current base URL for direct fetch calls (e.g., file upload). */
export function getApiBaseUrl() {
  return _baseUrl;
}

export const customInstance = async <T>({
  url,
  method,
  params,
  data,
  headers,
}: {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  params?: Record<string, string>;
  data?: unknown;
  headers?: Record<string, string>;
}): Promise<T> => {
  const searchParams = new URLSearchParams(params);
  const queryString = searchParams.toString() ? `?${searchParams.toString()}` : "";

  const client = typeof window !== "undefined" ? getSentinelClient() : null;
  const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};

  const isFormData = typeof FormData !== "undefined" && data instanceof FormData;

  const fetchHeaders: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...authHeaders,
    ...headers,
  };

  const response = await fetch(`${_baseUrl}${url}${queryString}`, {
    method,
    headers: fetchHeaders,
    ...(data
      ? { body: isFormData ? (data as FormData) : JSON.stringify(data) }
      : {}),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
};
