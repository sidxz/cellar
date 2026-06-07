"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { FavoriteResponse } from "@/shared/lib/api/model";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/** Widen this union as the backend FavoriteEntityType enum grows. */
export type FavoriteEntityType = "project";

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
  return useMutation({
    mutationFn: ({ entityId, favorited }: { entityId: string; favorited: boolean }) =>
      favorited
        ? customInstance<void>({
            url: `${API_V1}/favorites/${entityType}/${entityId}`,
            method: "DELETE",
          })
        : customInstance<FavoriteResponse>({
            url: `${API_V1}/favorites`,
            method: "POST",
            data: { entity_type: entityType, entity_id: entityId },
          }),
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
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
