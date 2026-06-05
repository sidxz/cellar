"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { DoseResponseCurve } from "../types";

const DOSE_RESPONSE_KEY = ["dose-response-curves"];

export function useDoseResponseByRun(runId: string | undefined) {
  return useQuery({
    queryKey: [...DOSE_RESPONSE_KEY, "run", runId],
    queryFn: () =>
      customInstance<DoseResponseCurve[]>({
        url: "/api/v1/dose-response-curves",
        method: "GET",
        params: { run_id: runId! },
      }),
    enabled: !!runId,
  });
}
