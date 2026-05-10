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
 */
export function useCollections(projectIds?: string[], options?: { includeAll?: boolean }) {
  const includeAll = options?.includeAll ?? false;
  const scope = !includeAll && projectIds && projectIds.length > 0 ? [...projectIds].sort() : null;
  return useQuery({
    queryKey: scope ? [...COLLECTIONS_KEY, { projectIds: scope }] : COLLECTIONS_KEY,
    queryFn: () =>
      customInstance<Collection[]>({
        url: "/api/v1/collections",
        method: "GET",
        ...(scope ? { params: { project_ids: scope } } : {}),
      }),
  });
}

export const useCollection = collectionHooks.useGet;
export const useCreateCollection = collectionHooks.useCreate;
export const useUpdateCollection = collectionHooks.useUpdate;
export const useDeleteCollection = collectionHooks.useDelete;
