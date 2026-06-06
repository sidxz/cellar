"use client";

import { cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete as cascadeDelete } from "@/shared/lib/api/admin/admin";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export interface CascadeDeleteOptions {
  entityType: string;
  entityId: string;
  typedName: string;
  reason: string;
}

export function useCascadeDelete(opts?: { onSuccess?: () => void }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entityType, entityId, typedName, reason }: CascadeDeleteOptions) => {
      await cascadeDelete(entityType, entityId, {
        typed_name: typedName,
        reason,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      showSuccess("Deleted");
      opts?.onSuccess?.();
    },
    onError: (err: unknown) => {
      showError(err instanceof Error ? err.message : "Failed");
    },
  });
}
