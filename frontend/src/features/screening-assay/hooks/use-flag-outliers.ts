"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { VISUALIZATION_DATASET_KEY } from "@/features/visualization/hooks/query-keys";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { FlagOutliersRequest, FlagOutliersResponse } from "@/shared/lib/api/model";
import {
  COMPOUND_CURVES_KEY,
  DOSE_RESPONSE_KEY,
  MELTING_ANALYSIS_KEY,
  MULTI_COMPOUND_CURVES_KEY,
  PLATE_MAP_KEY,
  PROTOCOL_ACTIVITY_KEY,
  READOUT_DATA_KEY,
  RUNS_KEY,
  RUN_KEY,
} from "./query-keys";

export type FlagOutliersInput = FlagOutliersRequest & { runId: string };

/** Flag wells of a run as outliers, or remove their flag; the run is then recalculated.
 *  POST /api/v1/runs/{runId}/outliers. A 409 means the run is locked or approved. */
export function useFlagOutliers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, ...body }: FlagOutliersInput) =>
      customInstance<FlagOutliersResponse>({
        url: `${API_V1}/runs/${runId}/outliers`,
        method: "POST",
        data: body,
      }),
    // As after a recompute: values, curves, compound activity, the run's plate QC, the
    // protocol's plate-QC averages and any workbench dataset holding the run all move.
    onSuccess: (_, { runId }) => {
      for (const queryKey of [
        READOUT_DATA_KEY,
        PLATE_MAP_KEY,
        DOSE_RESPONSE_KEY,
        COMPOUND_CURVES_KEY,
        MULTI_COMPOUND_CURVES_KEY,
        PROTOCOL_ACTIVITY_KEY,
        MELTING_ANALYSIS_KEY,
        RUNS_KEY,
        [...RUN_KEY, runId],
        VISUALIZATION_DATASET_KEY,
      ]) {
        qc.invalidateQueries({ queryKey });
      }
    },
  });
}
