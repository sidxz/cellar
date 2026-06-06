"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  ClassifyDoseResponseInput,
  DoseResponseCurve,
  RefitDoseResponseInput,
} from "../types";
import { DOSE_RESPONSE_KEY } from "./query-keys";

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
