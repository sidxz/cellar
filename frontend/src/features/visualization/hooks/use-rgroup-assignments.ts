"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { DecompositionAssignmentsResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

/** Every compound's R-groups of a finished decomposition run (one read, no paging). */
export function useRGroupAssignments(runId: string | null) {
  return useQuery({
    queryKey: ["sar", "decomposition", runId, "assignments"],
    enabled: runId !== null,
    queryFn: () =>
      customInstance<DecompositionAssignmentsResponse>({
        url: `${API_V1}/sar/decomposition/${runId}/assignments`,
        method: "GET",
      }),
    // A finished run never changes.
    staleTime: Number.POSITIVE_INFINITY,
  });
}
