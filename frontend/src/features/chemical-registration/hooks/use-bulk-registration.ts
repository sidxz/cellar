"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { getApiBaseUrl } from "@/shared/lib/api/custom-instance";
import type {
  BulkRegistrationAcceptedResponse,
  BulkRegistrationStatusResponse,
  BulkRegistrationResponse as GeneratedBulkRegistrationResponse,
} from "@/shared/lib/api/model";
import { getSentinelClient } from "@/shared/lib/auth/config";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MOLECULES_KEY } from "./query-keys";

// Backend DTOs — aliased from the orval-generated model (source of truth).
export type BulkRegistrationResponse = GeneratedBulkRegistrationResponse;
export type BulkRegistrationAccepted = BulkRegistrationAcceptedResponse;
export type BulkRegistrationStatus = BulkRegistrationStatusResponse;

/** Result type: either sync (201 with full results) or async (202 with workflow_id). */
export type BulkRegistrationResult =
  | { mode: "sync"; data: BulkRegistrationResponse }
  | { mode: "async"; workflowId: string };

export function useBulkRegistration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      fileFormat,
      originatingOrgId,
    }: {
      file: File;
      fileFormat: string;
      originatingOrgId: string;
    }): Promise<BulkRegistrationResult> => {
      const client = getSentinelClient();
      const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};

      const formData = new FormData();
      formData.append("file", file);
      formData.append("file_format", fileFormat);
      formData.append("originating_org_id", originatingOrgId);

      const res = await fetch(`${getApiBaseUrl()}/api/v1/bulk-registrations`, {
        method: "POST",
        headers: { ...authHeaders },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Upload failed: ${res.status}`);
      }

      if (res.status === 202) {
        const accepted = (await res.json()) as BulkRegistrationAccepted;
        return { mode: "async", workflowId: accepted.workflow_id };
      }

      // 201 — sync result
      const data = (await res.json()) as BulkRegistrationResponse;
      return { mode: "sync", data };
    },
    onSuccess: (result) => {
      if (result.mode === "sync") {
        qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      }
    },
  });
}

export function useBulkRegistrationStatus(workflowId: string | null) {
  const qc = useQueryClient();

  return useQuery({
    queryKey: ["bulk-registration", "status", workflowId],
    queryFn: async () => {
      const result = await customInstance<BulkRegistrationStatus>({
        url: `/api/v1/bulk-registrations/${workflowId}/status`,
        method: "GET",
      });
      if (result.status === "completed" || result.status === "completed_with_errors") {
        qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      }
      return result;
    },
    enabled: !!workflowId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "completed_with_errors") {
        return false;
      }
      return 2000;
    },
  });
}
