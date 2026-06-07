"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { DoseResponseCurve } from "../types";
import { DOSE_RESPONSE_KEY } from "./query-keys";

export function useDoseResponseByRun(runId: string | undefined) {
  return useQuery({
    queryKey: [...DOSE_RESPONSE_KEY, "run", runId],
    queryFn: () =>
      customInstance<DoseResponseCurve[]>({
        url: `${API_V1}/dose-response-curves`,
        method: "GET",
        params: { run_id: runId! },
      }),
    enabled: !!runId,
  });
}
