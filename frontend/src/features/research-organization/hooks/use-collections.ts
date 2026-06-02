"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { Collection, CreateCollectionInput, UpdateCollectionInput } from "../types";

const COLLECTIONS_KEY = ["collections"];

const collectionHooks = createCrudHooks<Collection, CreateCollectionInput, UpdateCollectionInput>({
  entityName: "Collection",
  baseUrl: "/api/v1/collections",
  queryKey: COLLECTIONS_KEY,
});

/**
 * Workspace collections list.
 *
 * - `projectIds` empty / undefined ⇒ workspace-wide list.
 * - `projectIds` non-empty ⇒ union of collections across those projects
 *   (defaults the search-panel picker to what's relevant to the user's
 *   selected programs without hiding cross-project collections behind
 *   a single click).
 * - `includeAll = true` overrides project scoping and returns the
 *   workspace-wide list — backs the per-picker "Show all (across projects)"
 *   toggle for chemists doing scaffold-hop / cross-program lookups.
 * - `tags` + `tagLogic` filter collections by assigned tags (passed to
 *   the backend `tags` / `tag_logic` query params).
 */
export function useCollections(
  projectIds?: string[],
  options?: { includeAll?: boolean; tags?: string[]; tagLogic?: "any" | "all" },
) {
  const includeAll = options?.includeAll ?? false;
  const scope = !includeAll && projectIds && projectIds.length > 0 ? [...projectIds].sort() : null;
  const tags = options?.tags?.length ? options.tags : null;
  return useQuery({
    queryKey: [
      ...COLLECTIONS_KEY,
      ...(scope ? [{ projectIds: scope }] : []),
      ...(tags ? [{ tags, tagLogic: options?.tagLogic ?? "any" }] : []),
    ],
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (scope) params.project_ids = scope;
      if (tags) { params.tags = tags; params.tag_logic = options?.tagLogic ?? "any"; }
      const resp = await customInstance<Collection[] | { items: Collection[] }>({
        url: "/api/v1/collections",
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
      return Array.isArray(resp) ? resp : resp.items;
    },
  });
}

export const useCollection = collectionHooks.useGet;
export const useCreateCollection = collectionHooks.useCreate;
export const useUpdateCollection = collectionHooks.useUpdate;
export const useDeleteCollection = collectionHooks.useDelete;
