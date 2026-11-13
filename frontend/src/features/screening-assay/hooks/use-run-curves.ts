"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { GetRunCurvesApiV1RunsRunIdCurvesGetView } from "@/shared/lib/api/model";
import type { RunCurves } from "../types";
import { MEASURED_CURVES_KEY } from "./query-keys";

export type CurveView = GetRunCurvesApiV1RunsRunIdCurvesGetView;

/** The run's measured curves for one signal, measured or as a derivative.
 *  GET /api/v1/runs/{runId}/curves?channel=&view=&window= (the API picks the
 *  first signal and, for a derivative, a default window when none is given,
 *  and reports the window it used). The previous curves stay on screen while
 *  the next ones load. */
export function useRunCurves(
  runId: string | undefined,
  params: { channel?: string; view?: CurveView; window?: number },
) {
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
