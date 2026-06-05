"use client";

import { cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost as cascadePreview } from "@/shared/lib/api/admin/admin";
import type { CascadeNodeResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export function useCascadePreview(entityType: string, entityId: string, enabled = true) {
  return useQuery<CascadeNodeResponse>({
    queryKey: ["cascade-preview", entityType, entityId],
    queryFn: () => cascadePreview(entityType, entityId),
    enabled,
  });
}
