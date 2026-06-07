"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ProtocolTargetRef } from "../types";
import { createTargetLinkHooks } from "./create-target-link-hooks";
import { PROTOCOLS_KEY, protocolTargetsKey } from "./query-keys";

/** Rich effective-target list with provenance (`is_direct` / `run_count`) for
 *  the design tab. The lightweight `protocol.targets` on GET /protocols/{id}
 *  does NOT carry provenance — this is the only source for it. */
export function useProtocolTargets(protocolId: string) {
  return useQuery({
    queryKey: protocolTargetsKey(protocolId),
    queryFn: () =>
      customInstance<ProtocolTargetRef[]>({
        url: `${API_V1}/protocols/${protocolId}/targets`,
        method: "GET",
      }),
    enabled: !!protocolId,
  });
}

const protocolTargetHooks = createTargetLinkHooks({
  entitySegment: "protocols",
  labels: { addedTo: "Target added to protocol", removedFrom: "Target removed from protocol" },
  // The rich targets list, the protocol detail, and the lists that render
  // target chips — once, not once per mutation.
  invalidateKeys: (protocolId) => [
    protocolTargetsKey(protocolId),
    [...PROTOCOLS_KEY, protocolId],
    PROTOCOLS_KEY,
  ],
});

/** One invalidation pass after a target-link gesture (single toggle or a
 *  batched diff). */
export const invalidateProtocolTargetQueries = protocolTargetHooks.invalidateTargetQueries;

/** Attach a direct target to a protocol (idempotent server-side). 409 when
 *  the protocol is locked or retired; 404 for an unknown target. Query
 *  invalidation is the CALLER's job via `invalidateProtocolTargetQueries` —
 *  batched diffs must invalidate once, not once per mutation. */
export const useAddProtocolTarget = protocolTargetHooks.useAddTarget;

/** Remove a direct target from a protocol. Inherited (run-union) targets are
 *  not removable here — they prune automatically when their runs drop them. */
export const useRemoveProtocolTarget = protocolTargetHooks.useRemoveTarget;
