"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { CreateSampleInput, Sample } from "../types";

const SAMPLES_KEY = ["samples"];

const sampleHooks = createCrudHooks<Sample, CreateSampleInput, Record<string, unknown>>({
  entityName: "Sample",
  baseUrl: "/api/v1/samples",
  queryKey: SAMPLES_KEY,
});

export const useSample = sampleHooks.useGet;
export const useCreateSample = sampleHooks.useCreate;

/** Custom hook — samples are listed under a batch, not flat. */
export function useSamplesByBatch(batchId: string | undefined) {
  return useQuery({
    queryKey: [...SAMPLES_KEY, "batch", batchId],
    queryFn: () =>
      customInstance<Sample[]>({
        url: `/api/v1/batches/${batchId}/samples`,
        method: "GET",
      }),
    enabled: !!batchId,
  });
}

// --- Custom action hooks (non-standard mutationFn signatures) ---

export function useAliquotSample() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sampleId, amount }: { sampleId: string; amount: number }) =>
      customInstance<Sample>({
        url: `/api/v1/samples/${sampleId}/aliquot`,
        method: "POST",
        data: { amount },
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: SAMPLES_KEY }); showSuccess("Aliquot complete"); },
  });
}

export function useMoveSample() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sampleId, locationId }: { sampleId: string; locationId: string | null }) =>
      customInstance<Sample>({
        url: `/api/v1/samples/${sampleId}/move`,
        method: "POST",
        data: { location_id: locationId },
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: SAMPLES_KEY }); showSuccess("Sample moved"); },
  });
}

export function useDisposeSample() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sampleId, reason }: { sampleId: string; reason?: string }) =>
      customInstance<Sample>({
        url: `/api/v1/samples/${sampleId}/dispose`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: SAMPLES_KEY }); showSuccess("Sample disposed"); },
  });
}

export function useQuarantineSample() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sampleId, reason }: { sampleId: string; reason: string }) =>
      customInstance<Sample>({
        url: `/api/v1/samples/${sampleId}/quarantine`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: SAMPLES_KEY }); showSuccess("Sample quarantined"); },
  });
}

export function useClearQuarantine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sampleId: string) =>
      customInstance<Sample>({
        url: `/api/v1/samples/${sampleId}/clear-quarantine`,
        method: "POST",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: SAMPLES_KEY }); showSuccess("Quarantine cleared"); },
  });
}
