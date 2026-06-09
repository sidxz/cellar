"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { type QueryClient, type QueryKey, useMutation } from "@tanstack/react-query";

/**
 * Builds the add/remove entity-link mutation pair (plus the once-per-gesture
 * invalidation helper) shared by the protocol/run target and collection
 * editors.
 *
 * Every such link exposes the same `POST`/`DELETE /{entitySegment}/{id}/{linkSegment}/{linkId}`
 * contract with the same success/error toast shape; only the URL segments, the
 * toast labels, and the invalidation cascade differ. The cascade is supplied
 * by the caller (`invalidateKeys`) because it is genuinely entity-specific —
 * run-link changes roll up into the protocol's effective links, so the run
 * cascade also invalidates the protocol queries.
 *
 * The returned member names keep their `Target` suffix (`useAddTarget`,
 * `useRemoveTarget`, `invalidateTargetQueries`) because every caller aliases
 * them to a domain-specific name on export — keeping them stable avoids churn
 * across the existing target consumers.
 */
export function createLinkHooks(config: {
  /** URL path segment for the owning entity, e.g. `"protocols"` or `"runs"`. */
  entitySegment: string;
  /** URL path segment for the linked entity, e.g. `"targets"` or `"collections"`. */
  linkSegment: string;
  /** Singular noun for toast copy, e.g. `"protocol"` or `"run"`. */
  labels: { addedTo: string; removedFrom: string };
  /** Query keys to invalidate (once) after a link gesture. */
  invalidateKeys: (entityId: string) => QueryKey[];
}) {
  const { entitySegment, linkSegment, labels, invalidateKeys } = config;

  /** One invalidation pass after a link gesture (single toggle or a batched
   *  diff) — once per gesture, not once per mutation. */
  const invalidateTargetQueries = (qc: QueryClient, entityId: string) =>
    Promise.all(invalidateKeys(entityId).map((queryKey) => qc.invalidateQueries({ queryKey })));

  /** Attach a link (idempotent server-side). 409 when the entity is locked
   *  or retired; 404 for an unknown link target. Query invalidation is the
   *  CALLER's job via the returned `invalidateTargetQueries` — batched diffs
   *  must invalidate once, not once per mutation. */
  const useAddTarget = (entityId: string) =>
    useMutation({
      mutationFn: (linkId: string) =>
        customInstance<void>({
          url: `${API_V1}/${entitySegment}/${entityId}/${linkSegment}/${linkId}`,
          method: "POST",
        }),
      onSuccess: () => {
        showSuccess(labels.addedTo);
      },
      onError: (err: Error) => {
        showError(err.message || "Failed to add");
      },
    });

  /** Remove a link. */
  const useRemoveTarget = (entityId: string) =>
    useMutation({
      mutationFn: (linkId: string) =>
        customInstance<void>({
          url: `${API_V1}/${entitySegment}/${entityId}/${linkSegment}/${linkId}`,
          method: "DELETE",
        }),
      onSuccess: () => {
        showSuccess(labels.removedFrom);
      },
      onError: (err: Error) => {
        showError(err.message || "Failed to remove");
      },
    });

  return { useAddTarget, useRemoveTarget, invalidateTargetQueries };
}
