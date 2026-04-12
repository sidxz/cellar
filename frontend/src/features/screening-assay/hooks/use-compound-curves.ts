"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { DoseResponseCurve } from "../types";

export function useCompoundCurves(
  protocolId: string,
  moleculeId: string | null
) {
  return useQuery({
    queryKey: ["compound-curves", protocolId, moleculeId],
    queryFn: () =>
      customInstance<DoseResponseCurve[]>({
        url: `/api/v1/protocols/${protocolId}/compounds/${moleculeId}/dose-response`,
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
export function useMultiCompoundCurves(
  protocolId: string,
  moleculeIds: string[]
) {
  const enabled = moleculeIds.length >= 2 && moleculeIds.length <= 5;
  return useQuery({
    queryKey: ["multi-compound-curves", protocolId, ...moleculeIds],
    queryFn: async () => {
      const results = await Promise.all(
        moleculeIds.map((mid) =>
          customInstance<DoseResponseCurve[]>({
            url: `/api/v1/protocols/${protocolId}/compounds/${mid}/dose-response`,
            method: "GET",
          })
        )
      );
      return results.flat();
    },
    enabled,
  });
}
