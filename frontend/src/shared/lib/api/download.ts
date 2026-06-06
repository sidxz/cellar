import { getApiBaseUrl, getAuthHeaders } from "./custom-instance";

/**
 * Trigger a browser "save as" for an already-in-memory `Blob`.
 *
 * Centralizes the `URL.createObjectURL` -> hidden `<a download>` -> `click()`
 * -> `revokeObjectURL` dance (with `appendChild`/`removeChild` so it works in
 * every browser) that was previously hand-inlined at every CSV-template /
 * JSON-export call site.
 */
export function saveBlob(blob: Blob, filename: string) {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

/**
 * Trigger a browser "save as" for in-memory text (e.g. a generated CSV
 * template). Wraps {@link saveBlob} with a text Blob.
 */
export function saveText(text: string, filename: string, mime = "text/csv") {
  saveBlob(new Blob([text], { type: mime }), filename);
}

/** Parse a server-provided `Content-Disposition` header into a filename. */
function filenameFromContentDisposition(disposition: string | null): string | undefined {
  if (!disposition) return undefined;
  const match = disposition.match(/filename="?([^"]+)"?/);
  return match?.[1];
}

/**
 * Download a file from an authenticated API endpoint.
 * Handles non-JSON responses (SDF, CSV, binary attachments, etc.) via
 * Blob + anchor click. Centralizes the auth-header + Content-Type wiring
 * that used to be reimplemented in feature-level fetch calls.
 *
 * When `filename` is omitted, the server-provided `Content-Disposition`
 * filename is used; if that's absent too, falls back to `fallbackFilename`.
 */
export async function downloadFile({
  url,
  method = "POST",
  data,
  filename,
  fallbackFilename = "download",
}: {
  url: string;
  method?: "GET" | "POST";
  data?: unknown;
  filename?: string;
  fallbackFilename?: string;
}) {
  const authHeaders = getAuthHeaders();

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
  const resolvedName =
    filename ??
    filenameFromContentDisposition(response.headers.get("content-disposition")) ??
    fallbackFilename;
  saveBlob(blob, resolvedName);
}
