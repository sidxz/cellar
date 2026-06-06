"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ProjectScopeStatsResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import { PROJECT_SCOPE_STATS_KEY } from "./query-keys";

// Alias the orval-generated DTO (CLAUDE.md: alias, never mirror).
export type ProjectScopeStats = ProjectScopeStatsResponse;

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
    queryKey: [...PROJECT_SCOPE_STATS_KEY, { projectIds: sortedIds }],
    queryFn: () =>
      customInstance<Record<string, ProjectScopeStats>>({
        url: `${API_V1}/projects/stats`,
        method: "GET",
        params: { project_ids: sortedIds },
      }),
    enabled,
    // staleTime omitted — inherits the global default (STALE_TIME.DEFAULT, 60s).
  });
}
