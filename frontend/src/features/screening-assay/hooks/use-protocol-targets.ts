"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const PROTOCOLS_KEY = ["protocols"];

/** Attach a direct target to a protocol (idempotent server-side). Rejected by
 *  the API (409) when the protocol is locked or retired. */
export function useAddProtocolTarget(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${protocolId}/targets/${targetId}`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] });
      showSuccess("Target added to protocol");
    },
  });
}

/** Remove a direct target from a protocol. Inherited (run-union) targets are
 *  not removable here — they prune automatically when their runs drop them. */
export function useRemoveProtocolTarget(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${protocolId}/targets/${targetId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] });
      showSuccess("Target removed from protocol");
    },
  });
}
