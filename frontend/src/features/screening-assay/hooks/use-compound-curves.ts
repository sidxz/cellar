"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { DoseResponseCurve } from "../types";
import { COMPOUND_CURVES_KEY, MULTI_COMPOUND_CURVES_KEY } from "./query-keys";

export function useCompoundCurves(protocolId: string, moleculeId: string | null) {
  return useQuery({
    queryKey: [...COMPOUND_CURVES_KEY, protocolId, moleculeId],
    queryFn: () =>
      customInstance<DoseResponseCurve[]>({
        url: `${API_V1}/protocols/${protocolId}/compounds/${moleculeId}/dose-response`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

/**
 * Fetch dose-response curves for multiple compounds in parallel.
 * Returns a flat array of all curves, each tagged with molecule_id.
 * Only enabled when moleculeIds has 2-5 entries.
 */
export function useMultiCompoundCurves(protocolId: string, moleculeIds: string[]) {
  const enabled = moleculeIds.length >= 2 && moleculeIds.length <= 5;
  return useQuery({
    queryKey: [...MULTI_COMPOUND_CURVES_KEY, protocolId, ...[...moleculeIds].sort()],
    queryFn: async () => {
      const results = await Promise.all(
        moleculeIds.map((mid) =>
          customInstance<DoseResponseCurve[]>({
            url: `${API_V1}/protocols/${protocolId}/compounds/${mid}/dose-response`,
            method: "GET",
          }),
        ),
      );
      return results.flat();
    },
    enabled,
  });
}
