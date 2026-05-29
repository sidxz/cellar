"use client";

import { useQuery } from "@tanstack/react-query";

import { getUnregisteredRowsApiV1CollectionImportPreviewsPreviewIdUnregisteredRowsGet as getUnregisteredRows } from "@/shared/lib/api/collection-import/collection-import";

/**
 * Fetch the unregistered-rows handoff bucket for a previous bulk-add preview.
 * Disabled when previewId is null (no preview run yet).
 */
export function useUnregisteredRows(previewId: string | null) {
  return useQuery({
    queryKey: ["unregistered-rows", previewId] as const,
    queryFn: () => getUnregisteredRows(previewId as string),
    enabled: previewId !== null,
  });
}
