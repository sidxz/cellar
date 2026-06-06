"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CddPlateImportAcceptedResponse,
  CddPlateImportStatusResponse,
  CddPlateImportSummary as CddPlateImportSummaryResponse,
} from "@/shared/lib/api/model";
import { isTerminalImportStatus } from "@/shared/lib/job-status";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { JOB_POLL_INTERVAL_MS } from "@/shared/lib/timing";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// ─── API DTOs (orval-generated; aliased per project rule) ────────────────────
// CDD plate-import response shapes are generated from the live backend OpenAPI
// — aliased to domain-friendly names so call sites don't churn.
export type CddPlateImportAccepted = CddPlateImportAcceptedResponse;
export type CddPlateImportStatus = CddPlateImportStatusResponse;
export type CddPlateImportSummary = CddPlateImportSummaryResponse;

export function useStartCddPlateImport() {
  return useMutation({
    mutationFn: () =>
      customInstance<CddPlateImportAccepted>({
        url: `${API_V1}/cdd-import/plates`,
        method: "POST",
      }),
  });
}

export function useCddPlateImportStatus(workflowId: string | null) {
  const qc = useQueryClient();

  return useQuery({
    queryKey: ["cdd-plate-import", "status", workflowId],
    queryFn: async () => {
      const result = await customInstance<CddPlateImportStatus>({
        url: `${API_V1}/cdd-import/plates/${workflowId}/status`,
        method: "GET",
      });
      if (isTerminalImportStatus(result.status)) {
        qc.invalidateQueries({ queryKey: ["plates"] });
      }
      return result;
    },
    enabled: !!workflowId,
    refetchInterval: (query) => {
      if (isTerminalImportStatus(query.state.data?.status)) {
        return false;
      }
      return JOB_POLL_INTERVAL_MS;
    },
  });
}

export function useCancelCddPlateImport() {
  return useMutation({
    mutationFn: (workflowId: string) =>
      customInstance({
        url: `${API_V1}/cdd-import/plates/${workflowId}/cancel`,
        method: "POST",
      }),
  });
}

export function useForceFailPlateImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) =>
      customInstance({
        url: `${API_V1}/cdd-import/plates/${importId}/force-fail`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cdd-plate-import", "history"] });
    },
  });
}

export function usePlateImportHistory() {
  return useQuery({
    queryKey: ["cdd-plate-import", "history"],
    queryFn: () =>
      customInstance<CddPlateImportSummary[]>({
        url: `${API_V1}/cdd-import/plates`,
        method: "GET",
      }),
    staleTime: STALE_TIME.SHORT,
  });
}
