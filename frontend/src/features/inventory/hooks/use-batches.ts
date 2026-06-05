"use client";

import { renderToast } from "@/features/inventory/components/mirror-summary-toast";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateBatchResponse } from "@/shared/lib/api/model/createBatchResponse";
import { showError, showSuccess } from "@/shared/lib/toast";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  Batch,
  BatchListItem,
  CreateBatchInput,
  PaginatedResponse,
  UpdateBatchInput,
} from "../types";

const batchHooks = createCrudHooks<Batch, CreateBatchInput, UpdateBatchInput>({
  entityName: "Batch",
  baseUrl: "/api/v1/batches",
  queryKey: ["batches"],
});

export const useBatch = batchHooks.useGet;
export const useUpdateBatch = batchHooks.useUpdate;

/**
 * Custom createBatch mutation typed against the `CreateBatchResponse` envelope.
 * The BE now returns `{ batch, mirror_summary }` so we can fire a toast when
 * auto-mirrors are created or skipped.
 */
export function useCreateBatch() {
  const qc = useQueryClient();
  return useMutation<CreateBatchResponse, Error, CreateBatchInput>({
    mutationFn: (data: CreateBatchInput) =>
      customInstance<CreateBatchResponse>({
        url: "/api/v1/batches",
        method: "POST",
        data,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["batches"] });
      showSuccess("Batch created");
      if (data?.mirror_summary) {
        renderToast(data.mirror_summary);
      }
    },
    onError: (err: Error) => {
      showError(err.message || "Failed to create Batch");
    },
  });
}

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
  tags?: string[];
  tagLogic?: "any" | "all";
}

export function useBatchesGlobal(params: BatchGlobalParams = {}) {
  const tags = params.tags?.length ? params.tags : null;
  const reqParams: Record<string, unknown> = {};
  if (params.search) reqParams.search = params.search;
  if (params.source?.length) reqParams.source = params.source.join(",");
  if (params.expiring_within_days != null)
    reqParams.expiring_within_days = String(params.expiring_within_days);
  if (params.cursor) reqParams.cursor = params.cursor;
  if (params.page_size) reqParams.page_size = String(params.page_size);
  if (tags) {
    reqParams.tags = tags;
    reqParams.tag_logic = params.tagLogic ?? "any";
  }

  return useQuery({
    queryKey: ["batches", "global", reqParams],
    queryFn: () =>
      customInstance<PaginatedResponse<BatchListItem>>({
        url: "/api/v1/batches",
        method: "GET",
        params: Object.keys(reqParams).length > 0 ? reqParams : undefined,
      }),
    placeholderData: keepPreviousData,
  });
}
