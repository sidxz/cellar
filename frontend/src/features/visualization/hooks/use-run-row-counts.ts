"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { RunRowCounts } from "../types";
import { VISUALIZATION_RUN_COUNTS_KEY } from "./query-keys";

export function useRunRowCounts(protocolId: string | null) {
  return useQuery({
    queryKey: [...VISUALIZATION_RUN_COUNTS_KEY, protocolId],
    enabled: protocolId !== null,
    queryFn: () =>
      customInstance<RunRowCounts>({
        url: `${API_V1}/visualization/protocols/${protocolId}/run-row-counts`,
        method: "GET",
      }),
  });
}
