import { getApiBaseUrl } from "./custom-instance";
import { getSentinelClient } from "@/shared/lib/auth/config";

/**
 * Download a file from an authenticated API endpoint.
 * Handles non-JSON responses (SDF, CSV, binary attachments, etc.) via
 * Blob + anchor click. Centralizes the auth-header + Content-Type wiring
 * that used to be reimplemented in feature-level fetch calls.
 */
export async function downloadFile({
  url,
  method = "POST",
  data,
  filename,
}: {
  url: string;
  method?: "GET" | "POST";
  data?: unknown;
  filename: string;
}) {
  const client = typeof window !== "undefined" ? getSentinelClient() : null;
  const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};

  // Only set Content-Type when sending a JSON body — GET requests with
  // a Content-Type can confuse some CORS preflights.
  const headers: Record<string, string> = { ...authHeaders };
  if (data !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${getApiBaseUrl()}${url}`, {
    method,
    headers,
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}
