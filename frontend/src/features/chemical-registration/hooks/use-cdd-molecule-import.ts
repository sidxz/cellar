"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { MOLECULES_KEY } from "./query-keys";

export interface CddMoleculeImportAccepted {
  import_id: string | null;
  workflow_id: string;
  status: string;
}

export interface CddMoleculeImportStatus {
  import_id: string;
  status: string;
  total_count: number;
  registered_count: number;
  duplicate_count: number;
  error_count: number;
  skipped_count: number;
  current_offset: number;
  pages_processed: number;
}

export interface CddMoleculeImportSummary {
  id: string;
  cdd_vault_id: string;
  import_mode: string;
  status: string;
  workflow_id: string | null;
  total_count: number;
  registered_count: number;
  duplicate_count: number;
  error_count: number;
  skipped_count: number;
  submitted_at: string;
  completed_at: string | null;
}

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
        url: "/api/v1/cdd-import/molecules",
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
        url: `/api/v1/cdd-import/molecules/${workflowId}/status`,
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
      if (
        status === "completed" ||
        status === "completed_with_errors" ||
        status === "failed"
      ) {
        return false;
      }
      return 2000;
    },
  });
}

export function useCancelCddMoleculeImport() {
  return useMutation({
    mutationFn: (workflowId: string) =>
      customInstance({
        url: `/api/v1/cdd-import/molecules/${workflowId}/cancel`,
        method: "POST",
      }),
  });
}

export function useForceFailImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) =>
      customInstance({
        url: `/api/v1/cdd-import/molecules/${importId}/force-fail`,
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
        url: "/api/v1/cdd-import/molecules",
        method: "GET",
      }),
    staleTime: 30_000,
  });
}
