"use client";

import {
  addBatchIdentifierApiV1BatchesBatchIdIdentifiersPost,
  getListBatchIdentifiersApiV1BatchesBatchIdIdentifiersGetQueryKey,
  removeBatchIdentifierApiV1BatchesBatchIdIdentifiersIdentifierIdDelete,
} from "@/shared/lib/api/batches/batches";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { BatchIdentifierResponse } from "@/shared/lib/api/model";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const BATCHES_KEY = ["batches"];

export function useBatchIdentifiers(batchId: string) {
  return useQuery({
    queryKey: getListBatchIdentifiersApiV1BatchesBatchIdIdentifiersGetQueryKey(batchId),
    queryFn: () =>
      customInstance<BatchIdentifierResponse[]>({
        url: `${API_V1}/batches/${batchId}/identifiers`,
        method: "GET",
      }),
    enabled: !!batchId,
  });
}

export function useAddBatchIdentifier(batchId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { identifier: string; identifier_type: string; source: string }) =>
      addBatchIdentifierApiV1BatchesBatchIdIdentifiersPost(batchId, data),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: getListBatchIdentifiersApiV1BatchesBatchIdIdentifiersGetQueryKey(batchId),
      });
      qc.invalidateQueries({ queryKey: [...BATCHES_KEY, batchId] });
    },
  });
}

export function useRemoveBatchIdentifier(batchId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (identifierId: string) =>
      removeBatchIdentifierApiV1BatchesBatchIdIdentifiersIdentifierIdDelete(batchId, identifierId),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: getListBatchIdentifiersApiV1BatchesBatchIdIdentifiersGetQueryKey(batchId),
      });
      qc.invalidateQueries({ queryKey: [...BATCHES_KEY, batchId] });
    },
  });
}
