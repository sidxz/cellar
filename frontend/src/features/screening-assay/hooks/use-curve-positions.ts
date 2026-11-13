"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { CurvePositions } from "../types";
import { MEASURED_CURVES_KEY } from "./query-keys";

/** The positions of a protocol's runs that have measured curves, without the
 *  curves, narrowed to some runs, some compounds or both.
 *  GET /api/v1/protocols/{protocolId}/curve-positions?run_ids=&molecule_ids= */
export function useCurvePositions(
  protocolId: string | undefined,
  filter: { runIds?: readonly string[]; moleculeIds?: readonly string[] },
  enabled = true,
) {
  return useQuery({
    queryKey: [...MEASURED_CURVES_KEY, "positions", protocolId, filter],
    queryFn: () =>
      customInstance<CurvePositions>({
        url: `${API_V1}/protocols/${protocolId}/curve-positions`,
        method: "GET",
        params: { run_ids: filter.runIds, molecule_ids: filter.moleculeIds },
      }),
    enabled: enabled && !!protocolId,
    placeholderData: keepPreviousData,
  });
}
