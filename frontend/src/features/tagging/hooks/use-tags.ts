"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { TaggableEntityType } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import type { Tag } from "../types";

const tagHooks = createCrudHooks<
  Tag,
  { key: string; value?: string | null },
  { key: string; value?: string | null }
>({
  entityName: "Tag",
  baseUrl: `${API_V1}/tags`,
  queryKey: ["tags"],
});

export const useRenameTag = tagHooks.useUpdate;
export const useDeleteTag = tagHooks.useDelete;
export const useMergeTags = () => tagHooks.useAction("merge", "Tags merged");

export function useTags(params?: {
  q?: string;
  mine?: boolean;
  limit?: number;
  /** Only tags in use on this entity type (e.g. "Molecule"). */
  entityType?: TaggableEntityType;
}) {
  const search: Record<string, string> = {};
  if (params?.q) search.q = params.q;
  if (params?.mine) search.mine = "true";
  if (params?.limit) search.limit = String(params.limit);
  if (params?.entityType) search.entity_type = params.entityType;
  return useQuery({
    queryKey: ["tags", search],
    queryFn: () => customInstance<Tag[]>({ url: `${API_V1}/tags`, method: "GET", params: search }),
  });
}
