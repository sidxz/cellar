"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { type QueryClient, useMutation, useQuery } from "@tanstack/react-query";
import type { ProtocolTargetRef } from "../types";
import { PROTOCOLS_KEY, protocolTargetsKey } from "./query-keys";

/** Rich effective-target list with provenance (`is_direct` / `run_count`) for
 *  the design tab. The lightweight `protocol.targets` on GET /protocols/{id}
 *  does NOT carry provenance — this is the only source for it. */
export function useProtocolTargets(protocolId: string) {
  return useQuery({
    queryKey: protocolTargetsKey(protocolId),
    queryFn: () =>
      customInstance<ProtocolTargetRef[]>({
        url: `/api/v1/protocols/${protocolId}/targets`,
        method: "GET",
      }),
    enabled: !!protocolId,
  });
}

/** One invalidation pass after a target-link gesture (single toggle or a
 *  batched diff): the rich targets list, the protocol detail, and the lists
 *  that render target chips — once, not once per mutation. */
export function invalidateProtocolTargetQueries(qc: QueryClient, protocolId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: protocolTargetsKey(protocolId) }),
    qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] }),
    qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  ]);
}

/** Attach a direct target to a protocol (idempotent server-side). 409 when
 *  the protocol is locked or retired; 404 for an unknown target. Query
 *  invalidation is the CALLER's job via `invalidateProtocolTargetQueries` —
 *  batched diffs must invalidate once, not once per mutation. */
export function useAddProtocolTarget(protocolId: string) {
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${protocolId}/targets/${targetId}`,
        method: "POST",
      }),
    onSuccess: () => {
      showSuccess("Target added to protocol");
    },
    onError: (err: Error) => {
      showError(err.message || "Failed to add target");
    },
  });
}

/** Remove a direct target from a protocol. Inherited (run-union) targets are
 *  not removable here — they prune automatically when their runs drop them. */
export function useRemoveProtocolTarget(protocolId: string) {
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${protocolId}/targets/${targetId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      showSuccess("Target removed from protocol");
    },
    onError: (err: Error) => {
      showError(err.message || "Failed to remove target");
    },
  });
}
