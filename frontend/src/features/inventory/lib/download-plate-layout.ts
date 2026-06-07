import { API_V1 } from "@/shared/lib/api/custom-instance";
import { downloadFile } from "@/shared/lib/api/download";

/**
 * Download a registered plate's well-map as a round-trippable CSV/XLSX file.
 *
 * Delegates to the shared {@link downloadFile} helper, which performs the
 * authenticated fetch, honors the server's `Content-Disposition` filename, and
 * triggers the browser download. Falls back to `plate_well_map.<format>` when
 * the server omits a filename.
 */
export async function downloadPlateLayout(plateId: string, format: "csv" | "xlsx"): Promise<void> {
  await downloadFile({
    url: `${API_V1}/plates/${plateId}/export?format=${format}`,
    method: "GET",
    fallbackFilename: `plate_well_map.${format}`,
  });
}
