"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateSynthesisRequestInput,
  SynthesisRequest,
  SynthesisRequestSummary,
} from "../types/synthesis-request";

const SYNTHESIS_REQUESTS_KEY = ["synthesis-requests"];

const synthHooks = createCrudHooks<
  SynthesisRequest,
  CreateSynthesisRequestInput,
  Record<string, unknown>
>({
  entityName: "Synthesis request",
  baseUrl: "/api/v1/synthesis-requests",
  queryKey: SYNTHESIS_REQUESTS_KEY,
});

/** Custom list — returns SynthesisRequestSummary[], supports status/molecule_id params. */
export function useSynthesisRequests(params?: {
  status?: string;
  molecule_id?: string;
}) {
  return useQuery({
    queryKey: [...SYNTHESIS_REQUESTS_KEY, params],
    queryFn: () =>
      customInstance<SynthesisRequestSummary[]>({
        url: "/api/v1/synthesis-requests",
        method: "GET",
        params,
      }),
  });
}

export const useSynthesisRequest = synthHooks.useGet;
export const useCreateSynthesisRequest = synthHooks.useCreate;
export const useDeleteSynthesisRequest = synthHooks.useDelete;

// --- Simple state transitions (callers pass plain id string) ---

export function useSubmitSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/submit`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request submitted");
    },
  });
}

export function useApproveSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/approve`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request approved");
    },
  });
}

export function useCancelSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/cancel`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request cancelled");
    },
  });
}

// --- Complex state transitions (callers pass { id, ...payload }) ---

export function useRejectSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/reject`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request rejected");
    },
  });
}

export function useAssignSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      assignment_type,
      assigned_to,
      assigned_org_id,
    }: {
      id: string;
      assignment_type: string;
      assigned_to?: string | null;
      assigned_org_id?: string | null;
    }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/assign`,
        method: "POST",
        data: { assignment_type, assigned_to, assigned_org_id },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request assigned");
    },
  });
}

export function useStartSynthesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      proposed_route_id,
    }: {
      id: string;
      proposed_route_id?: string | null;
    }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/start`,
        method: "POST",
        data: { proposed_route_id },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis started");
    },
  });
}

export function useFlagInfeasible() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      feasibility_status,
      feasibility_notes,
    }: {
      id: string;
      feasibility_status: string;
      feasibility_notes?: string | null;
    }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/flag-infeasible`,
        method: "POST",
        data: { feasibility_status, feasibility_notes },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request flagged as infeasible");
    },
  });
}

export function useCompleteSynthesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      actual_cost_value,
      actual_cost_unit,
    }: {
      id: string;
      actual_cost_value?: number | null;
      actual_cost_unit?: string | null;
    }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/complete`,
        method: "POST",
        data: { actual_cost_value, actual_cost_unit },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis completed");
    },
  });
}

export function useFulfillSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, batch_id }: { id: string; batch_id: string }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/fulfill`,
        method: "POST",
        data: { batch_id },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request fulfilled");
    },
  });
}

export function useFailSynthesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}/fail`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request marked as failed");
    },
  });
}

export function useUpdateSynthesisRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: string;
      purpose?: string;
      priority?: string;
      amount_value?: number;
      amount_unit?: string;
      target_purity?: number | null;
    }) =>
      customInstance<SynthesisRequest>({
        url: `/api/v1/synthesis-requests/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_REQUESTS_KEY });
      showSuccess("Synthesis request updated");
    },
  });
}
