"use client";

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { Batch, BatchListItem, CreateBatchInput, PaginatedResponse, UpdateBatchInput } from "../types";

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

// ---------------------------------------------------------------------------
// Global batches list (paginated, filterable)
// ---------------------------------------------------------------------------

export interface BatchGlobalParams {
  search?: string;
  source?: string[];
  expiring_within_days?: number;
  cursor?: string;
  page_size?: number;
}

export function useBatchesGlobal(params: BatchGlobalParams = {}) {
  const searchParams: Record<string, string> = {};
  if (params.search) searchParams.search = params.search;
  if (params.source?.length) searchParams.source = params.source.join(",");
  if (params.expiring_within_days != null)
    searchParams.expiring_within_days = String(params.expiring_within_days);
  if (params.cursor) searchParams.cursor = params.cursor;
  if (params.page_size) searchParams.page_size = String(params.page_size);

  return useQuery({
    queryKey: ["batches", "global", searchParams],
    queryFn: () =>
      customInstance<PaginatedResponse<BatchListItem>>({
        url: "/api/v1/batches",
        method: "GET",
        params: searchParams,
      }),
    placeholderData: keepPreviousData,
  });
}
