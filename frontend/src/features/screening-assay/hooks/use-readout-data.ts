"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ReadoutData } from "../types";
import { READOUT_DATA_KEY } from "./query-keys";

export function useReadoutDataByRun(runId: string | undefined) {
  return useQuery({
    queryKey: [...READOUT_DATA_KEY, "run", runId],
    queryFn: () =>
      customInstance<ReadoutData[]>({
        url: `${API_V1}/readout-data`,
        method: "GET",
        params: { run_id: runId! },
      }),
    enabled: !!runId,
  });
}
