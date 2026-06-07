"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { FavoriteEntityType, FavoriteResponse } from "@/shared/lib/api/model";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/**
 * Alias of the orval-generated enum (`@/shared/lib/api/model`); tracks the
 * backend `FavoriteEntityType` automatically as new values are added.
 */
export type { FavoriteEntityType };

export const favoritesKey = (entityType: FavoriteEntityType) => ["favorites", entityType];

/** Set of the current user's favorited entity ids of the given type. */
export function useFavorites(entityType: FavoriteEntityType) {
  return useQuery({
    queryKey: favoritesKey(entityType),
    queryFn: async () => {
      const list = await customInstance<FavoriteResponse[]>({
        url: `${API_V1}/favorites`,
        method: "GET",
        params: { entity_type: entityType },
      });
      return new Set(list.map((f) => f.entity_id));
    },
  });
}

/**
 * Toggle a favorite with an optimistic update.
 *
 * Call `mutate({ entityId, favorited })` where `favorited` is the CURRENT
 * state: `true` → remove (DELETE), `false` → add (POST).
 */
export function useToggleFavorite(entityType: FavoriteEntityType) {
  const qc = useQueryClient();
  const key = favoritesKey(entityType);
  type Vars = { entityId: string; favorited: boolean };
  type Ctx = { prev: Set<string> | undefined };
  return useMutation<void, unknown, Vars, Ctx>({
    mutationFn: async ({ entityId, favorited }) => {
      if (favorited) {
        await customInstance<void>({
          url: `${API_V1}/favorites/${entityType}/${entityId}`,
          method: "DELETE",
        });
      } else {
        await customInstance<FavoriteResponse>({
          url: `${API_V1}/favorites`,
          method: "POST",
          data: { entity_type: entityType, entity_id: entityId },
        });
      }
    },
    onMutate: async ({ entityId, favorited }) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Set<string>>(key);
      const next = new Set(prev ?? []);
      if (favorited) next.delete(entityId);
      else next.add(entityId);
      qc.setQueryData(key, next);
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      // Always undo the optimistic write. When the cache was empty at onMutate
      // time `prev` is undefined; `setQueryData(key, undefined)` is a no-op in
      // query-core, so remove the entry to truly reset rather than leak it.
      if (ctx?.prev === undefined) qc.removeQueries({ queryKey: key, exact: true });
      else qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
