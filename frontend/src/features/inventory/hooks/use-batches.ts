"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { Batch, CreateBatchInput, UpdateBatchInput } from "../types";

const BATCHES_KEY = ["batches"];

export function useBatchesByMolecule(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...BATCHES_KEY, "molecule", moleculeId],
    queryFn: () =>
      customInstance<Batch[]>({
        url: `/api/v1/molecules/${moleculeId}/batches`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

export function useBatch(id: string | undefined) {
  return useQuery({
    queryKey: [...BATCHES_KEY, id],
    queryFn: () =>
      customInstance<Batch>({
        url: `/api/v1/batches/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateBatchInput) =>
      customInstance<Batch>({
        url: "/api/v1/batches",
        method: "POST",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: BATCHES_KEY }); showSuccess("Batch created"); },
  });
}

export function useUpdateBatch(batchId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateBatchInput) =>
      customInstance<Batch>({
        url: `/api/v1/batches/${batchId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: BATCHES_KEY }); showSuccess("Batch updated"); },
  });
}
