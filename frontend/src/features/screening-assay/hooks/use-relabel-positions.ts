"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RelabelPositionsRequest } from "@/shared/lib/api/model";
import type { RelabelResult } from "../types";
import {
  DOSE_RESPONSE_KEY,
  MEASURED_CURVES_KEY,
  MELTING_ANALYSIS_KEY,
  PLATE_MAP_KEY,
  READOUT_DATA_KEY,
  RUN_KEY,
} from "./query-keys";

/** Change positions' label, note, role, batch or concentration.
 *  POST /api/v1/runs/{runId}/relabel-positions. A 409 means a position no
 *  longer holds the values the edit started from, or a campaign uses it. */
export function useRelabelPositions(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RelabelPositionsRequest) =>
      customInstance<RelabelResult>({
        url: `${API_V1}/runs/${runId}/relabel-positions`,
        method: "POST",
        data: body,
      }),
    onSuccess: () => {
      for (const queryKey of [
        READOUT_DATA_KEY,
        DOSE_RESPONSE_KEY,
        PLATE_MAP_KEY,
        MEASURED_CURVES_KEY,
        [...MELTING_ANALYSIS_KEY, runId],
        [...RUN_KEY, runId],
      ]) {
        qc.invalidateQueries({ queryKey });
      }
    },
  });
}
