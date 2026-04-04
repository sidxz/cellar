// Custom fetch instance for orval-generated API client.
// Auth tokens injected from the shared Sentinel SDK singleton.

import { getSentinelClient } from "@/shared/lib/auth/config";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

  const response = await fetch(`${BASE_URL}${url}${queryString}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...headers,
    },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json() as Promise<T>;
};
