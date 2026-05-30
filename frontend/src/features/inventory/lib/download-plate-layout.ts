import { getApiBaseUrl } from "@/shared/lib/api/custom-instance";
import { getSentinelClient } from "@/shared/lib/auth/config";

/**
 * Download a registered plate's well-map as a round-trippable CSV/XLSX file.
 *
 * The export endpoint streams a binary file, so we can't use the JSON
 * `customInstance` — we do a direct authenticated fetch (reusing the Sentinel
 * auth headers) and trigger a browser download from the blob.
 */
export async function downloadPlateLayout(plateId: string, format: "csv" | "xlsx"): Promise<void> {
  const client = typeof window !== "undefined" ? getSentinelClient() : null;
  const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};

  const res = await fetch(`${getApiBaseUrl()}/api/v1/plates/${plateId}/export?format=${format}`, {
    headers: authHeaders,
  });
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }

  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? `plate_well_map.${format}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
