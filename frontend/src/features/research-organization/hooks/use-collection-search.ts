"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { EnrichedSearchResponse } from "./use-search";
import type { ExecuteSearchInput } from "../types";

export interface UseCollectionSearchOptions {
  /** Page size — collections rarely exceed a few thousand mols so default 1000 is plenty for V1. */
  limit?: number;
}

/**
 * Fetches the enriched molecule list for a collection by posting a single
 * `{ type: "collection", collection_id }` criterion to the search engine.
 * Returns the same `EnrichedSearchResponse` shape `/search` consumes, so
 * downstream views (CardGrid, ResultsGrid) reuse the existing types.
 */
export function useCollectionSearch(
  collectionId: string,
  opts: UseCollectionSearchOptions = {},
) {
  const { limit = 1000 } = opts;

  return useQuery({
    queryKey: ["collection-search", collectionId, limit],
    enabled: Boolean(collectionId),
    queryFn: async () => {
      const input: ExecuteSearchInput = {
        query: {
          logic: "and",
          criteria: [{ type: "collection", collection_id: collectionId }],
        },
      };
      return customInstance<EnrichedSearchResponse>({
        url: "/api/v1/search/execute",
        method: "POST",
        data: input,
        params: { limit: String(limit) },
      });
    },
  });
}
