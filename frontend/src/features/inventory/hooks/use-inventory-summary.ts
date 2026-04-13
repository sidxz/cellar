"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { InventorySummary } from "../types";

export function useInventorySummary() {
  return useQuery({
    queryKey: ["inventory", "summary"],
    queryFn: () =>
      customInstance<InventorySummary>({
        url: "/api/v1/inventory/summary",
        method: "GET",
      }),
    staleTime: 30_000,
  });
}
