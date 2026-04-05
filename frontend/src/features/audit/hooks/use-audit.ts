"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { AuditOperation } from "../types";

const AUDIT_KEY = ["audit"];

export function useAuditOperations(filters?: {
  entity_type?: string;
  entity_id?: string;
  user_id?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: [...AUDIT_KEY, filters],
    queryFn: () =>
      customInstance<AuditOperation[]>({
        url: "/api/v1/audit",
        method: "GET",
        params: filters
          ? Object.fromEntries(
              Object.entries(filters)
                .filter(([, v]) => v !== undefined && v !== "")
                .map(([k, v]) => [k, String(v)]),
            )
          : undefined,
      }),
  });
}

export function useAuditByEntity(entityType: string, entityId: string | undefined) {
  return useQuery({
    queryKey: [...AUDIT_KEY, "entity", entityType, entityId],
    queryFn: () =>
      customInstance<AuditOperation[]>({
        url: "/api/v1/audit",
        method: "GET",
        params: { entity_type: entityType, entity_id: entityId! },
      }),
    enabled: !!entityId,
  });
}
