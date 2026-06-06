"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { JOB_POLL_INTERVAL_MS } from "@/shared/lib/timing";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface CddPlateImportAccepted {
  import_id: string | null;
  workflow_id: string;
  status: string;
}

export interface CddPlateImportStatus {
  import_id: string;
  status: string;
  total_count: number;
  plates_registered: number;
  plates_duplicate: number;
  plates_error: number;
  wells_mapped: number;
  wells_unresolved: number;
  current_offset: number;
  pages_processed: number;
}

export interface CddPlateImportSummary {
  id: string;
  cdd_vault_id: string;
  status: string;
  workflow_id: string | null;
  total_count: number;
  plates_registered: number;
  plates_duplicate: number;
  plates_error: number;
  wells_mapped: number;
  wells_unresolved: number;
  submitted_at: string;
  completed_at: string | null;
}

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
      if (
        result.status === "completed" ||
        result.status === "completed_with_errors" ||
        result.status === "failed"
      ) {
        qc.invalidateQueries({ queryKey: ["plates"] });
      }
      return result;
    },
    enabled: !!workflowId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "completed_with_errors" || status === "failed") {
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
    staleTime: 30_000,
  });
}
