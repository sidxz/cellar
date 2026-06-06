"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { useQuery } from "@tanstack/react-query";
import type { InventorySummary } from "../types";

export function useInventorySummary() {
  return useQuery({
    queryKey: ["inventory", "summary"],
    queryFn: () =>
      customInstance<InventorySummary>({
        url: `${API_V1}/inventory/summary`,
        method: "GET",
      }),
    staleTime: STALE_TIME.SHORT,
  });
}
