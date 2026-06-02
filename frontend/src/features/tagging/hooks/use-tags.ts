"use client";

import { useQuery } from "@tanstack/react-query";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { Tag } from "../types";

const tagHooks = createCrudHooks<
  Tag,
  { key: string; value?: string | null },
  { key: string; value?: string | null }
>({
  entityName: "Tag",
  baseUrl: "/api/v1/tags",
  queryKey: ["tags"],
});

export const useRenameTag = tagHooks.useUpdate;
export const useDeleteTag = tagHooks.useDelete;
export const useMergeTags = () => tagHooks.useAction("merge", "Tags merged");

export function useTags(params?: { q?: string; mine?: boolean; limit?: number }) {
  const search: Record<string, string> = {};
  if (params?.q) search.q = params.q;
  if (params?.mine) search.mine = "true";
  if (params?.limit) search.limit = String(params.limit);
  return useQuery({
    queryKey: ["tags", search],
    queryFn: () =>
      customInstance<Tag[]>({ url: "/api/v1/tags", method: "GET", params: search }),
  });
}
