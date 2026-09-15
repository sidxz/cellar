"use client";

import { cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost as cascadePreview } from "@/shared/lib/api/admin/admin";
import type { CascadePreviewResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export function useCascadePreview(entityType: string, entityId: string, enabled = true) {
  return useQuery<CascadePreviewResponse>({
    queryKey: ["cascade-preview", entityType, entityId],
    queryFn: () => cascadePreview(entityType, entityId),
    enabled,
    // The global default is 60s (see query-defaults.ts), but this gates the
    // Force delete button: reopening the dialog after resolving a blocker
    // must refetch, not serve the blockers that were just fixed.
    staleTime: 0,
  });
}
