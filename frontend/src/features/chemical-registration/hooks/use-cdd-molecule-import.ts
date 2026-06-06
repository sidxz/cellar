"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CddMoleculeImportAcceptedResponse,
  CddMoleculeImportStatusResponse,
  CddMoleculeImportSummary as CddMoleculeImportSummaryResponse,
} from "@/shared/lib/api/model";
import { JOB_POLL_INTERVAL_MS } from "@/shared/lib/timing";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MOLECULES_KEY } from "./query-keys";

// ─── API DTOs (orval-generated; aliased per project rule) ────────────────────
// CDD molecule-import response shapes are generated from the live backend
// OpenAPI — aliased to domain-friendly names so call sites don't churn.
export type CddMoleculeImportAccepted = CddMoleculeImportAcceptedResponse;
export type CddMoleculeImportStatus = CddMoleculeImportStatusResponse;
export type CddMoleculeImportSummary = CddMoleculeImportSummaryResponse;

export function useStartCddMoleculeImport() {
  return useMutation({
    mutationFn: ({
      originatingOrgId,
      importMode,
      filterCriteria,
      maxMolecules,
    }: {
      originatingOrgId: string;
      importMode?: "full_vault" | "sync";
      filterCriteria?: Record<string, unknown>;
      maxMolecules?: number;
    }) =>
      customInstance<CddMoleculeImportAccepted>({
        url: `${API_V1}/cdd-import/molecules`,
        method: "POST",
        data: {
          originating_org_id: originatingOrgId,
          import_mode: importMode ?? "full_vault",
          filter_criteria: filterCriteria ?? null,
          max_molecules: maxMolecules ?? null,
        },
      }),
  });
}

export function useCddMoleculeImportStatus(workflowId: string | null) {
  const qc = useQueryClient();

  return useQuery({
    queryKey: ["cdd-molecule-import", "status", workflowId],
    queryFn: async () => {
      const result = await customInstance<CddMoleculeImportStatus>({
        url: `${API_V1}/cdd-import/molecules/${workflowId}/status`,
        method: "GET",
      });
      // When complete, invalidate the molecule list
      if (
        result.status === "completed" ||
        result.status === "completed_with_errors" ||
        result.status === "failed"
      ) {
        qc.invalidateQueries({ queryKey: MOLECULES_KEY });
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

export function useCancelCddMoleculeImport() {
  return useMutation({
    mutationFn: (workflowId: string) =>
      customInstance({
        url: `${API_V1}/cdd-import/molecules/${workflowId}/cancel`,
        method: "POST",
      }),
  });
}

export function useForceFailImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) =>
      customInstance({
        url: `${API_V1}/cdd-import/molecules/${importId}/force-fail`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cdd-molecule-import", "history"] });
    },
  });
}

export function useImportHistory() {
  return useQuery({
    queryKey: ["cdd-molecule-import", "history"],
    queryFn: () =>
      customInstance<CddMoleculeImportSummary[]>({
        url: `${API_V1}/cdd-import/molecules`,
        method: "GET",
      }),
    staleTime: 30_000,
  });
}
