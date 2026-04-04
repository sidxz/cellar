"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateDoseResponseCurveInput, DoseResponseCurve } from "../types";

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

export function useCreateDoseResponseCurve() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDoseResponseCurveInput) =>
      customInstance<DoseResponseCurve>({
        url: "/api/v1/dose-response-curves",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY }),
  });
}
