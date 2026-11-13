"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RunCurves } from "../types";
import { MEASURED_CURVES_KEY } from "./query-keys";

/** The run's measured curves for one signal.
 *  GET /api/v1/runs/{runId}/curves?channel= (the API picks the first signal
 *  when none is given). The previous signal stays on screen while the next
 *  one loads. */
export function useRunCurves(runId: string | undefined, params: { channel?: string }) {
  return useQuery({
    queryKey: [...MEASURED_CURVES_KEY, runId, params],
    queryFn: () =>
      customInstance<RunCurves>({
        url: `${API_V1}/runs/${runId}/curves`,
        method: "GET",
        params,
      }),
    enabled: !!runId,
    placeholderData: keepPreviousData,
  });
}
