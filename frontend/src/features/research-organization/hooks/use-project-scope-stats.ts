"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

export interface ProjectScopeStats {
  molecule_count: number;
  protocol_count: number;
  run_count: number;
}

const STATS_KEY = ["projects", "scope-stats"];

/**
 * Fetches molecule / protocol / run counts for each given project so the
 * project chip in the search panel can show the size of the haystack
 * up-front (helps a chemist size their query before firing it).
 *
 * Counts are project totals — unconditional on the rest of the search
 * criteria. The chip answers "how big is this program?", not "how many
 * results will my query return".
 *
 * Empty projectIds → no fetch, returns {} immediately.
 */
export function useProjectScopeStats(projectIds: string[]) {
  const sortedIds = [...projectIds].sort();
  const enabled = sortedIds.length > 0;
  return useQuery({
    queryKey: [...STATS_KEY, { projectIds: sortedIds }],
    queryFn: () =>
      customInstance<Record<string, ProjectScopeStats>>({
        url: "/api/v1/projects/stats",
        method: "GET",
        params: { project_ids: sortedIds },
      }),
    enabled,
    staleTime: 60_000,
  });
}
