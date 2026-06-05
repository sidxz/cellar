"use client";

import {
  useBulkAddBatchIdentifiersApiV1BatchesIdentifiersBulkPost,
  usePreviewBulkAddBatchIdentifiersApiV1BatchesIdentifiersPreviewBulkPost,
} from "@/shared/lib/api/batches/batches";
import type {
  BulkAddBatchIdentifiersRequest,
  BulkAddBatchIdentifiersResponse,
  RowOutcomeResponse,
} from "@/shared/lib/api/model";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Dry-run preview of a bulk batch-identifier import.
 * Returns per-row outcomes without committing.
 */
export function usePreviewBulkIdentifiers() {
  return usePreviewBulkAddBatchIdentifiersApiV1BatchesIdentifiersPreviewBulkPost();
}

/**
 * Commit a bulk batch-identifier import.
 * Persists only the `resolved` rows; invalidates batch caches on success.
 */
export function useCommitBulkIdentifiers() {
  const qc = useQueryClient();
  return useBulkAddBatchIdentifiersApiV1BatchesIdentifiersBulkPost({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["batch-identifiers"] });
        qc.invalidateQueries({ queryKey: ["batch"] });
        qc.invalidateQueries({ queryKey: ["batches"] });
      },
    },
  });
}

// Re-export types for convenience
export type { BulkAddBatchIdentifiersRequest, BulkAddBatchIdentifiersResponse, RowOutcomeResponse };
