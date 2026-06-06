"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ProtocolStats } from "../types";

export function useProtocolStats(protocolId: string) {
  return useQuery({
    queryKey: ["protocol-stats", protocolId],
    queryFn: () =>
      customInstance<ProtocolStats>({
        url: `${API_V1}/protocols/${protocolId}/stats`,
        method: "GET",
      }),
  });
}
