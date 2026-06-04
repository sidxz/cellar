"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import type { TaggedEntityResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

/** A tagged entity row from the cross-entity browse endpoint. */
export type TaggedEntity = TaggedEntityResponse;

export function useTagEntities(tagId: string | undefined, types?: string[]) {
  return useQuery({
    queryKey: ["tag-entities", tagId, types ?? null],
    enabled: !!tagId,
    queryFn: () =>
      customInstance<TaggedEntity[]>({
        url: `/api/v1/tags/${tagId}/entities`,
        method: "GET",
        ...(types?.length ? { params: { types } } : {}),
      }),
  });
}
