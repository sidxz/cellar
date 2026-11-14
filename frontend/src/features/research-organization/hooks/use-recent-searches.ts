"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RecentSearchResponse, RecordRecentSearchBody } from "@/shared/lib/api/model";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { RECENT_SEARCHES_KEY } from "./query-keys";

/** A search the user ran — its query and table set-up, as a saved search stores them. */
export type RecentSearch = RecentSearchResponse;

const URL = `${API_V1}/recent-searches`;

/** The current user's newest searches in this workspace. */
export function useRecentSearches(limit = 10) {
  return useQuery({
    queryKey: [...RECENT_SEARCHES_KEY, limit],
    queryFn: () => customInstance<RecentSearch[]>({ url: URL, method: "GET", params: { limit } }),
  });
}

/** Remember a search that just ran. Fire-and-forget and quiet on failure (not
 *  a mutation: the global mutation handler would toast) — losing one history
 *  entry must never get in the way of the search itself. */
export function useRecordRecentSearch() {
  const queryClient = useQueryClient();
  return useCallback(
    (body: RecordRecentSearchBody) => {
      customInstance<RecentSearch>({ url: URL, method: "POST", data: body })
        .then(() => queryClient.invalidateQueries({ queryKey: RECENT_SEARCHES_KEY }))
        .catch((error: unknown) => console.warn("Search not added to recent searches", error));
    },
    [queryClient],
  );
}

export function useClearRecentSearches() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customInstance<void>({ url: URL, method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: RECENT_SEARCHES_KEY }),
  });
}
