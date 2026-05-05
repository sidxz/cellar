"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess, showError } from "@/shared/lib/toast";
import type { RegisterMoleculeInput, RegistrationResponse } from "../types";
import type {
  BulkProgress,
  ConfirmMergesResponse,
  MergeDecision,
} from "../types/registration-wizard";

import { MOLECULES_KEY } from "./query-keys";

const BULK_REG_KEY = ["bulk-registrations"];

// ─── Single Registration ────────────────────────────────────────────────────

/** POST /api/v1/molecules — returns full RegistrationResponse including action fields. */
export function useSubmitRegistration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterMoleculeInput) =>
      customInstance<RegistrationResponse>({
        url: "/api/v1/molecules",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
    },
    onError: (err: Error) => {
      showError(err.message ?? "Registration failed");
    },
  });
}

// ─── Bulk Registration ──────────────────────────────────────────────────────

export interface StartBulkRegistrationInput {
  file: File;
  originating_org_id: string | null;
  file_format?: "csv" | "xlsx" | "sdf";
}

/** POST /api/v1/bulk-registrations — multipart/form-data upload. */
export function useStartBulkRegistration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      originating_org_id,
      file_format = "csv",
    }: StartBulkRegistrationInput) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("file_format", file_format);
      if (originating_org_id) {
        formData.append("originating_org_id", originating_org_id);
      }
      return customInstance<{ workflow_id: string; status: string }>({
        url: "/api/v1/bulk-registrations",
        method: "POST",
        data: formData,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: BULK_REG_KEY });
      showSuccess("Bulk registration job started");
    },
    onError: (err: Error) => {
      showError(err.message ?? "Failed to start bulk registration");
    },
  });
}

/** GET /api/v1/bulk-registrations/{workflowId} — polls every 3 s while job is active. */
export function useBulkRegistrationStatus(
  workflowId: string | null,
  enabled: boolean
) {
  return useQuery({
    queryKey: [...BULK_REG_KEY, workflowId],
    queryFn: () =>
      customInstance<BulkProgress>({
        url: `/api/v1/bulk-registrations/${workflowId}/status`,
        method: "GET",
      }),
    enabled: enabled && !!workflowId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      return 3_000;
    },
  });
}

// ─── Bulk Merge Confirmation ────────────────────────────────────────────────

export interface ConfirmMergesInput {
  decisions: MergeDecision[];
}

/** POST /api/v1/bulk-registrations/{workflowId}/confirm-merges */
export function useConfirmMerges(workflowId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ConfirmMergesInput) =>
      customInstance<ConfirmMergesResponse>({
        url: `/api/v1/bulk-registrations/${workflowId}/confirm-merges`,
        method: "POST",
        data: input,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      qc.invalidateQueries({ queryKey: BULK_REG_KEY });
      showSuccess(
        `Merges processed: ${data.confirmed_count} confirmed, ${data.rejected_count} rejected`
      );
    },
    onError: (err: Error) => {
      showError(err.message ?? "Failed to process merge decisions");
    },
  });
}
