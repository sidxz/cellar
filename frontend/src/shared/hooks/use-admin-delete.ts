"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  adminHardDeleteApiV1AdminEntityTypeEntityIdDelete as adminHardDelete,
} from "@/shared/lib/api/admin/admin";
import type { BlockerPayload } from "@/shared/lib/api/model";

export interface AdminDeleteOptions {
  entityType: string;
  entityId: string;
  reason: string;
}

export type AdminDeleteBlocker = BlockerPayload;

export function useAdminDelete(opts?: { onSuccess?: () => void }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entityType, entityId, reason }: AdminDeleteOptions) => {
      await adminHardDelete(entityType, entityId, { reason });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Deleted");
      opts?.onSuccess?.();
    },
    onError: (err: unknown) => {
      const data = (err as any)?.response?.data;
      if (data?.error === "delete_blocked_by_dependencies") return;
      toast.error((err as any)?.message ?? "Failed to delete");
    },
  });
}
