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
