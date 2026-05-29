"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { bulkAddToCollectionApiV1CollectionsCollectionIdMoleculesBulkPost as bulkAddToCollection } from "@/shared/lib/api/collections/collections";
import type { BulkAddRequestBody, BulkAddResponse } from "@/shared/lib/api/model";

/**
 * Commit a bulk add-to-collection import.
 * Persists `resolved` rows; invalidates collection caches on success.
 */
export function useCommitCollectionImport(collectionId: string) {
  const qc = useQueryClient();
  return useMutation<BulkAddResponse, Error, BulkAddRequestBody>({
    mutationFn: (body) => bulkAddToCollection(collectionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["collection", collectionId] });
      qc.invalidateQueries({ queryKey: ["collection-search", collectionId] });
      qc.invalidateQueries({ queryKey: ["collections"] });
    },
  });
}

export type { BulkAddRequestBody, BulkAddResponse };
