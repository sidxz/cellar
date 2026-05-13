"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateMapResponse } from "../types";

const PLATE_MAP_KEY = ["plate-map"];

export function usePlateMap(runId: string | undefined) {
  return useQuery({
    queryKey: [...PLATE_MAP_KEY, runId],
    queryFn: () =>
      customInstance<PlateMapResponse>({
        url: `/api/v1/runs/${runId}/plate-map`,
        method: "GET",
      }),
    enabled: !!runId,
  });
}
