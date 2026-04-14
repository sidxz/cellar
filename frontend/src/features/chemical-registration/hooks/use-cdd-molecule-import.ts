"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";

const MOLECULES_KEY = ["molecules"];

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

export function useStartCddMoleculeImport() {
  return useMutation({
    mutationFn: ({
      originatingOrgId,
      importMode,
      filterCriteria,
      maxMolecules,
    }: {
      originatingOrgId: string;
      importMode?: string;
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
