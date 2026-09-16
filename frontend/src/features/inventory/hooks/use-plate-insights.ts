"use client";

import type { PlateInsightsResponse } from "@/shared/lib/api/model";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

export type PlateInsights = PlateInsightsResponse;

export function usePlateInsights(orgId: string | undefined) {
  return useQuery({
    queryKey: ["plate-insights", orgId],
    queryFn: ({ signal }) =>
      customInstance<PlateInsights>({
        url: `${API_V1}/plates/insights`,
        method: "GET",
        params: { org_id: orgId as string },
        signal,
      }),
    enabled: !!orgId,
  });
}
