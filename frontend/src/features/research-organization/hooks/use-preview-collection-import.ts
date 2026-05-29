"use client";

import { useMutation } from "@tanstack/react-query";

import { previewBulkAddToCollectionApiV1CollectionsCollectionIdMoleculesPreviewBulkPost as previewBulkAddToCollection } from "@/shared/lib/api/collections/collections";
import type { BulkAddRequestBody, BulkAddResponse } from "@/shared/lib/api/model";

/**
 * Dry-run preview of a bulk add-to-collection import.
 * Returns per-row outcomes + unregistered-row handoff bucket without committing.
 */
export function usePreviewCollectionImport(collectionId: string) {
  return useMutation<BulkAddResponse, Error, BulkAddRequestBody>({
    mutationFn: (body) => previewBulkAddToCollection(collectionId, body),
  });
}

export type { BulkAddRequestBody, BulkAddResponse };
