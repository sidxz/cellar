"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { TaggedEntityResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

/** A tagged entity row from the cross-entity browse endpoint. */
export type TaggedEntity = TaggedEntityResponse;

export function useTagEntities(
  tagIds: string[],
  tagLogic: "any" | "all" = "any",
  types?: string[],
) {
  const ids = tagIds.length ? tagIds : null;
  return useQuery({
    queryKey: ["tag-entities", ids, tagLogic, types ?? null],
    enabled: !!ids,
    queryFn: () =>
      customInstance<TaggedEntity[]>({
        url: `${API_V1}/tags/entities`,
        method: "GET",
        params: {
          tags: tagIds,
          tag_logic: tagLogic,
          ...(types?.length ? { types } : {}),
        },
      }),
  });
}
