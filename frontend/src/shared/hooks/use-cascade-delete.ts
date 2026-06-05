"use client";

import { cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete as cascadeDelete } from "@/shared/lib/api/admin/admin";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

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
      toast.success("Deleted");
      opts?.onSuccess?.();
    },
    onError: (err: unknown) => {
      toast.error((err as any)?.message ?? "Failed");
    },
  });
}
