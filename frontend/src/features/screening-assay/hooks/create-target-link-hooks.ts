"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { type QueryClient, type QueryKey, useMutation } from "@tanstack/react-query";

/**
 * Builds the add/remove target-link mutation pair (plus the once-per-gesture
 * invalidation helper) shared by protocol and run target editors.
 *
 * Both entities expose the same `POST`/`DELETE /{segment}/{id}/targets/{targetId}`
 * contract with the same success/error toast shape; only the URL segment, the
 * toast labels, and the invalidation cascade differ. The cascade is supplied
 * by the caller (`invalidateKeys`) because it is genuinely entity-specific —
 * run-target changes roll up into the protocol's effective targets, so the run
 * cascade also invalidates the protocol queries.
 */
export function createTargetLinkHooks(config: {
  /** URL path segment, e.g. `"protocols"` or `"runs"`. */
  entitySegment: string;
  /** Singular noun for toast copy, e.g. `"protocol"` or `"run"`. */
  labels: { addedTo: string; removedFrom: string };
  /** Query keys to invalidate (once) after a target-link gesture. */
  invalidateKeys: (entityId: string) => QueryKey[];
}) {
  const { entitySegment, labels, invalidateKeys } = config;

  /** One invalidation pass after a target-link gesture (single toggle or a
   *  batched diff) — once per gesture, not once per mutation. */
  const invalidateTargetQueries = (qc: QueryClient, entityId: string) =>
    Promise.all(invalidateKeys(entityId).map((queryKey) => qc.invalidateQueries({ queryKey })));

  /** Attach a target (idempotent server-side). 409 when the entity is locked
   *  or retired; 404 for an unknown target. Query invalidation is the CALLER's
   *  job via the returned `invalidateTargetQueries` — batched diffs must
   *  invalidate once, not once per mutation. */
  const useAddTarget = (entityId: string) =>
    useMutation({
      mutationFn: (targetId: string) =>
        customInstance<void>({
          url: `${API_V1}/${entitySegment}/${entityId}/targets/${targetId}`,
          method: "POST",
        }),
      onSuccess: () => {
        showSuccess(labels.addedTo);
      },
      onError: (err: Error) => {
        showError(err.message || "Failed to add target");
      },
    });

  /** Remove a target. */
  const useRemoveTarget = (entityId: string) =>
    useMutation({
      mutationFn: (targetId: string) =>
        customInstance<void>({
          url: `${API_V1}/${entitySegment}/${entityId}/targets/${targetId}`,
          method: "DELETE",
        }),
      onSuccess: () => {
        showSuccess(labels.removedFrom);
      },
      onError: (err: Error) => {
        showError(err.message || "Failed to remove target");
      },
    });

  return { useAddTarget, useRemoveTarget, invalidateTargetQueries };
}
