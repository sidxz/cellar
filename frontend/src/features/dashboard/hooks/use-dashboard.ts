"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { DashboardStats } from "../types";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () =>
      customInstance<DashboardStats>({
        url: "/api/v1/dashboard/stats",
        method: "GET",
      }),
  });
}
