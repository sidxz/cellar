"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  DoseResponseCurve,
  RefitDoseResponseInput,
  ClassifyDoseResponseInput,
} from "../types";

const DOSE_RESPONSE_KEY = ["dose-response-curves"];

export function useRefitDoseResponse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      curveId,
      input,
    }: {
      curveId: string;
      input: RefitDoseResponseInput;
    }) =>
      customInstance<DoseResponseCurve>({
        url: `/api/v1/dose-response-curves/${curveId}/refit`,
        method: "POST",
        data: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY }),
  });
}

export function useClassifyDoseResponse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      curveId,
      input,
    }: {
      curveId: string;
      input: ClassifyDoseResponseInput;
    }) =>
      customInstance<DoseResponseCurve>({
        url: `/api/v1/dose-response-curves/${curveId}/classify`,
        method: "PATCH",
        data: input,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY }),
  });
}
