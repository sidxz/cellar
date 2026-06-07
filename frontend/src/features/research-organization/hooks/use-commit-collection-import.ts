"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { bulkAddToCollectionApiV1CollectionsCollectionIdMoleculesBulkPost as bulkAddToCollection } from "@/shared/lib/api/collections/collections";
import type { BulkAddRequestBody, BulkAddResponse } from "@/shared/lib/api/model";
import { COLLECTIONS_KEY, COLLECTION_KEY, COLLECTION_SEARCH_KEY } from "./query-keys";

/**
 * Commit a bulk add-to-collection import.
 * Persists `resolved` rows; invalidates collection caches on success.
 */
export function useCommitCollectionImport(collectionId: string) {
  const qc = useQueryClient();
  return useMutation<BulkAddResponse, Error, BulkAddRequestBody>({
    mutationFn: (body) => bulkAddToCollection(collectionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...COLLECTION_KEY, collectionId] });
      qc.invalidateQueries({ queryKey: [...COLLECTION_SEARCH_KEY, collectionId] });
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
    },
  });
}

export type { BulkAddRequestBody, BulkAddResponse };
