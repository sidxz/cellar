/**
 * Batch-fetch 2D structure depictions from the backend.
 * Returns a map of SMILES → base64 PNG string.
 */

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";

interface DepictResponse {
  images: Record<string, string>;
}

export async function fetchStructureImages(
  smilesSet: string[],
  width = 150,
  height = 100,
): Promise<Record<string, string>> {
  const unique = [...new Set(smilesSet.filter(Boolean))];
  if (unique.length === 0) return {};

  const resp = await customInstance<DepictResponse>({
    url: `${API_V1}/molecules/depict`,
    method: "POST",
    data: { smiles_list: unique, width, height },
  });
  return resp.images;
}
