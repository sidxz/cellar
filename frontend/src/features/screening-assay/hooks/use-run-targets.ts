"use client";

import { createTargetLinkHooks } from "./create-target-link-hooks";
import { PROTOCOLS_KEY, RUNS_KEY } from "./query-keys";

const runTargetHooks = createTargetLinkHooks({
  entitySegment: "runs",
  labels: { addedTo: "Target added to run", removedFrom: "Target removed from run" },
  // The run detail, the run lists, and — because run targets roll up into the
  // protocol's effective targets — the protocol queries. Once per gesture.
  invalidateKeys: (runId) => [[...RUNS_KEY, runId], RUNS_KEY, PROTOCOLS_KEY],
});

/** One invalidation pass after a run-target gesture (single toggle or a
 *  batched diff). */
export const invalidateRunTargetQueries = runTargetHooks.invalidateTargetQueries;

/** Link a target to a run (idempotent server-side). 409 when the run is
 *  locked; 404 for an unknown target. Query invalidation is the CALLER's job
 *  via `invalidateRunTargetQueries` — batched diffs must invalidate once. */
export const useAddRunTarget = runTargetHooks.useAddTarget;

/** Remove a target from a run. If no other run (and no direct link) references
 *  it, the protocol auto-prunes it from its effective targets. */
export const useRemoveRunTarget = runTargetHooks.useRemoveTarget;
