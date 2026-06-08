"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { EffectiveCollectionCoverage } from "../types";
import { PROTOCOLS_KEY } from "./query-keys";

export function useProtocolCollectionCoverage(protocolId: string) {
  return useQuery({
    queryKey: [...PROTOCOLS_KEY, protocolId, "collection-coverage"],
    queryFn: () =>
      customInstance<EffectiveCollectionCoverage[]>({
        url: `${API_V1}/protocols/${protocolId}/collection-coverage`,
        method: "GET",
      }),
    enabled: Boolean(protocolId),
  });
}
