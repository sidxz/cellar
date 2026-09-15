"use client";

import { cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost as cascadePreview } from "@/shared/lib/api/admin/admin";
import type { CascadePreviewResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export function useCascadePreview(entityType: string, entityId: string, enabled = true) {
  return useQuery<CascadePreviewResponse>({
    queryKey: ["cascade-preview", entityType, entityId],
    queryFn: () => cascadePreview(entityType, entityId),
    enabled,
  });
}
