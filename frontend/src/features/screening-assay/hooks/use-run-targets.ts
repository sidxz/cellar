"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { type QueryClient, useMutation } from "@tanstack/react-query";

const RUNS_KEY = ["runs"];
const PROTOCOLS_KEY = ["protocols"];

/** One invalidation pass after a run-target gesture (single toggle or a
 *  batched diff): the run detail, the run lists, and — because run targets
 *  roll up into the protocol's effective targets — the protocol queries.
 *  Once per gesture, not once per mutation. */
export function invalidateRunTargetQueries(qc: QueryClient, runId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: [...RUNS_KEY, runId] }),
    qc.invalidateQueries({ queryKey: RUNS_KEY }),
    qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  ]);
}

/** Link a target to a run (idempotent server-side). 409 when the run is
 *  locked; 404 for an unknown target. Query invalidation is the CALLER's job
 *  via `invalidateRunTargetQueries` — batched diffs must invalidate once. */
export function useAddRunTarget(runId: string) {
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/runs/${runId}/targets/${targetId}`,
        method: "POST",
      }),
    onSuccess: () => {
      showSuccess("Target added to run");
    },
    onError: (err: Error) => {
      showError(err.message || "Failed to add target");
    },
  });
}

/** Remove a target from a run. If no other run (and no direct link) references
 *  it, the protocol auto-prunes it from its effective targets. */
export function useRemoveRunTarget(runId: string) {
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/runs/${runId}/targets/${targetId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      showSuccess("Target removed from run");
    },
    onError: (err: Error) => {
      showError(err.message || "Failed to remove target");
    },
  });
}
