"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ActivitySummaryV2 } from "../types";

export function useProtocolActivity(protocolId: string) {
  return useQuery({
    queryKey: ["protocol-activity", protocolId],
    queryFn: () =>
      customInstance<ActivitySummaryV2>({
        url: `/api/v1/protocols/${protocolId}/activity-summary`,
        method: "GET",
      }),
  });
}
