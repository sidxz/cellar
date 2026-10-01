"use client";

import { useDebounce } from "@/shared/hooks/use-debounce";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { CountSearchResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { SearchQuery } from "../types";

// Alias the orval-generated DTO (CLAUDE.md: alias, never mirror).
type CountResponse = CountSearchResponse;

const COUNT_KEY = ["search", "count"];

/**
 * Fetches a live "Search N compounds" preview for the draft query in the
 * search panel. Powered by POST /api/v1/search/count, which runs only the
 * SELECT COUNT(*) -- no row materialization, similarity scoring, or activity
 * enrichment.
 *
 * - Debounces on the serialized query so 5-10 quick edits collapse into one
 *   round-trip.
 * - keepPreviousData ghosts the count during refetch instead of flashing 0.
 * - Disabled when the query has no criteria -- the badge is hidden in that
 *   case (see SearchForm).
 */
export function useSearchCount(query: SearchQuery, enabled: boolean) {
  const serialized = JSON.stringify(query);
  const debouncedKey = useDebounce(serialized, SEARCH_DEBOUNCE_MS);

  // Gate on the debounced query too: when the first criterion appears,
  // `enabled` flips immediately while the key still holds the old empty
  // query — which would fetch (and flash) the whole-workspace count.
  const debouncedQuery = JSON.parse(debouncedKey) as SearchQuery;

  const result = useQuery({
    queryKey: [...COUNT_KEY, debouncedKey],
    queryFn: () =>
      customInstance<CountResponse>({
        url: `${API_V1}/search/count`,
        method: "POST",
        data: { query: debouncedQuery },
      }),
    enabled: enabled && debouncedQuery.criteria.length > 0,
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME.SHORT,
    retry: false,
  });
  // True while the form has moved on but the debounced key hasn't caught up —
  // the result (and any error) still describes the previous query.
  return { ...result, isDebouncing: serialized !== debouncedKey };
}
