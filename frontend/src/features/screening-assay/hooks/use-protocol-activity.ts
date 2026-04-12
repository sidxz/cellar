"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { ActivitySummary } from "../types";

export function useProtocolActivity(
  protocolId: string,
  readoutName?: string
) {
  return useQuery({
    queryKey: ["protocol-activity", protocolId, readoutName],
    queryFn: () =>
      customInstance<ActivitySummary>({
        url: `/api/v1/protocols/${protocolId}/activity-summary`,
        method: "GET",
        params: readoutName ? { readout_name: readoutName } : undefined,
      }),
  });
}
