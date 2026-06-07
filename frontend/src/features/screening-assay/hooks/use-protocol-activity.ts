"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ActivitySummaryV2 } from "../types";
import { PROTOCOL_ACTIVITY_KEY } from "./query-keys";

export function useProtocolActivity(protocolId: string) {
  return useQuery({
    queryKey: [...PROTOCOL_ACTIVITY_KEY, protocolId],
    queryFn: () =>
      customInstance<ActivitySummaryV2>({
        url: `${API_V1}/protocols/${protocolId}/activity-summary`,
        method: "GET",
      }),
  });
}
