"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

/**
 * Fetches the number of distinct protocols each molecule has been tested in.
 *
 * When ``projectId`` is supplied the count is scoped to protocols linked to
 * that project; otherwise a workspace-wide count is returned.
 *
 * Molecules with no DR data are returned with count=0 so callers never need
 * to handle missing keys.
 */
export function useProtocolTestCounts(
  moleculeIds: string[],
  projectId: string | null | undefined,
): UseQueryResult<Record<string, number>> {
  // Sort for stable query-key identity regardless of insertion order.
  const sortedIds = [...moleculeIds].sort();

  return useQuery({
    queryKey: ["protocol-test-counts", sortedIds.join(","), projectId ?? null],
    enabled: sortedIds.length > 0,
    queryFn: async () => {
      const res = await customInstance<{ counts: Record<string, number> }>({
        url: `${API_V1}/molecules/test-counts`,
        method: "POST",
        data: {
          molecule_ids: sortedIds,
          project_id: projectId ?? null,
        },
      });
      return res.counts;
    },
  });
}
