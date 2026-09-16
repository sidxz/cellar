"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { LinkRunPlateBody, RunPlateLinkResponse } from "@/shared/lib/api/model";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PlateMapResponse } from "../types";
import { PLATE_MAP_KEY } from "./query-keys";

export function usePlateMap(runId: string | undefined) {
  return useQuery({
    queryKey: [...PLATE_MAP_KEY, runId],
    queryFn: () =>
      customInstance<PlateMapResponse>({
        url: `${API_V1}/runs/${runId}/plate-map`,
        method: "GET",
      }),
    enabled: !!runId,
  });
}

/** Link a run plate to an inventory plate by barcode or plate label. */
export function useLinkRunPlate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ plateId, barcode }: { plateId: string; barcode: string }) =>
      customInstance<RunPlateLinkResponse>({
        url: `${API_V1}/runs/${runId}/plates/${plateId}:link`,
        method: "POST",
        data: { barcode } satisfies LinkRunPlateBody,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_MAP_KEY });
      showSuccess("Plate linked");
    },
  });
}

export function useUnlinkRunPlate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ plateId }: { plateId: string }) =>
      customInstance<RunPlateLinkResponse>({
        url: `${API_V1}/runs/${runId}/plates/${plateId}:unlink`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_MAP_KEY });
      showSuccess("Plate unlinked");
    },
  });
}
