"use client";

import { adminHardDeleteApiV1AdminEntityTypeEntityIdDelete as adminHardDelete } from "@/shared/lib/api/admin/admin";
import { ApiError } from "@/shared/lib/api/custom-instance";
import type { BlockedByDependenciesResponse, BlockerPayload } from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export interface AdminDeleteOptions {
  entityType: string;
  entityId: string;
  reason: string;
}

export type AdminDeleteBlocker = BlockerPayload;

/**
 * Narrows an unknown error to the backend's 409 "blocked by dependencies"
 * payload. The blocker contract lives at the TOP LEVEL of the JSON body
 * (`{error: "delete_blocked_by_dependencies", message, blockers}`) — not under
 * `detail` — and is carried on {@link ApiError.body}. Returns the typed
 * response when matched, else `null`.
 */
export function getDeleteBlockedError(err: unknown): BlockedByDependenciesResponse | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body as Partial<BlockedByDependenciesResponse> | null | undefined;
  if (body?.error === "delete_blocked_by_dependencies" && Array.isArray(body.blockers)) {
    return body as BlockedByDependenciesResponse;
  }
  return null;
}

export function useAdminDelete(opts?: { onSuccess?: () => void }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entityType, entityId, reason }: AdminDeleteOptions) => {
      await adminHardDelete(entityType, entityId, { reason });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      showSuccess("Deleted");
      opts?.onSuccess?.();
    },
    onError: (err: unknown) => {
      // Blocked deletes are surfaced by the caller (it renders the blocker
      // list from the rethrown error); stay silent here rather than firing a
      // misleading generic toast.
      if (getDeleteBlockedError(err)) return;
      showError(err instanceof Error ? err.message : "Failed to delete");
    },
  });
}
