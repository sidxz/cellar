"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { DashboardStats } from "../types";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () =>
      customInstance<DashboardStats>({
        url: `${API_V1}/dashboard/stats`,
        method: "GET",
      }),
  });
}
