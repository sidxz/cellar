"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ExecuteSearchInput } from "../types";
import { COLLECTION_SEARCH_KEY } from "./query-keys";
import type { EnrichedSearchResponse } from "./use-search";

export interface UseCollectionSearchOptions {
  /**
   * Page size. The BE auto-relaxes the generic search cap (200) to
   * COLLECTION_FETCH_MAX_PAGE_SIZE (10K) when the query is a single
   * `{type: "collection"}` criterion, so we can ask atomically. Default
   * 10000 covers every realistic curated chemistry collection.
   */
  limit?: number;
}

/**
 * Fetches the enriched molecule list for a collection by posting a single
 * `{ type: "collection", collection_id }` criterion to the search engine.
 * Returns the same `EnrichedSearchResponse` shape `/search` consumes, so
 * downstream views (CardGrid, ResultsGrid) reuse the existing types.
 */
export function useCollectionSearch(collectionId: string, opts: UseCollectionSearchOptions = {}) {
  const { limit = 10000 } = opts;

  return useQuery({
    queryKey: [...COLLECTION_SEARCH_KEY, collectionId, limit],
    enabled: Boolean(collectionId),
    queryFn: async () => {
      const input: ExecuteSearchInput = {
        query: {
          logic: "and",
          criteria: [{ type: "collection", collection_id: collectionId }],
        },
      };
      return customInstance<EnrichedSearchResponse>({
        url: `${API_V1}/search/execute`,
        method: "POST",
        data: input,
        params: { limit: String(limit) },
      });
    },
  });
}
