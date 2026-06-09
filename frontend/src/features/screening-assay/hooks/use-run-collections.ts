"use client";

import { createLinkHooks } from "./create-link-hooks";
import { PROTOCOLS_KEY, RUNS_KEY } from "./query-keys";

const runCollectionHooks = createLinkHooks({
  entitySegment: "runs",
  linkSegment: "collections",
  labels: { addedTo: "Collection added to run", removedFrom: "Collection removed from run" },
  // The run detail, the run lists, and — because run collection coverage rolls
  // up into the protocol's effective coverage — the protocol queries. Once per
  // gesture, mirroring the run-target cascade.
  invalidateKeys: (runId) => [[...RUNS_KEY, runId], RUNS_KEY, PROTOCOLS_KEY],
});

/** One invalidation pass after a run-collection gesture (single toggle or a
 *  batched diff). */
export const invalidateRunCollectionQueries = runCollectionHooks.invalidateTargetQueries;

/** Attach a collection to a run (idempotent server-side). 409 when the run is
 *  locked; 404 for an unknown collection. Query invalidation is the CALLER's
 *  job via `invalidateRunCollectionQueries` — batched diffs must invalidate
 *  once, not once per mutation. */
export const useAddRunCollection = runCollectionHooks.useAddTarget;

/** Remove a collection from a run. */
export const useRemoveRunCollection = runCollectionHooks.useRemoveTarget;
