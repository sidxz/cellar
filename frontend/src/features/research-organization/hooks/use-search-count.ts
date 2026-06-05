"use client";

import { useDebounce } from "@/shared/hooks/use-debounce";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { SearchQuery } from "../types";

interface CountResponse {
  total_count: number;
}

const COUNT_KEY = ["search", "count"];
const DEBOUNCE_MS = 250;

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
  const debouncedKey = useDebounce(serialized, DEBOUNCE_MS);

  return useQuery({
    queryKey: [...COUNT_KEY, debouncedKey],
    queryFn: () =>
      customInstance<CountResponse>({
        url: "/api/v1/search/count",
        method: "POST",
        data: { query: JSON.parse(debouncedKey) as SearchQuery },
      }),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
}
