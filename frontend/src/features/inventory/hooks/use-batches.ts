"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { Batch, CreateBatchInput, UpdateBatchInput } from "../types";

const batchHooks = createCrudHooks<Batch, CreateBatchInput, UpdateBatchInput>({
  entityName: "Batch",
  baseUrl: "/api/v1/batches",
  queryKey: ["batches"],
});

export const useBatch = batchHooks.useGet;
export const useCreateBatch = batchHooks.useCreate;
export const useUpdateBatch = batchHooks.useUpdate;

/** Custom hook — batches are listed under a molecule, not flat. */
export function useBatchesByMolecule(moleculeId: string | undefined) {
  return useQuery({
    queryKey: ["batches", "molecule", moleculeId],
    queryFn: () =>
      customInstance<Batch[]>({
        url: `/api/v1/molecules/${moleculeId}/batches`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
