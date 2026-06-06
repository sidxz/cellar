"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const RUNS_KEY = ["runs"];
const PROTOCOLS_KEY = ["protocols"];

/** Link a target to a run (idempotent server-side). Rejected by the API (409)
 *  when the run is locked. A run's targets roll up into its protocol's
 *  effective targets, so the protocol queries are invalidated too. */
export function useAddRunTarget(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/runs/${runId}/targets/${targetId}`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: [...RUNS_KEY, runId] });
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Target added to run");
    },
  });
}

/** Remove a target from a run. If no other run (and no direct link) references
 *  it, the protocol auto-prunes it from its effective targets. */
export function useRemoveRunTarget(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/runs/${runId}/targets/${targetId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: [...RUNS_KEY, runId] });
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Target removed from run");
    },
  });
}
