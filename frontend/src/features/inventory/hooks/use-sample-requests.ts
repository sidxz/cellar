"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { CreateSampleRequestInput, SampleRequest } from "../types/sample-request";

const SAMPLE_REQUESTS_KEY = ["sample-requests"];

export function useSampleRequests(status?: string) {
  return useQuery({
    queryKey: [...SAMPLE_REQUESTS_KEY, { status }],
    queryFn: () =>
      customInstance<SampleRequest[]>({
        url: "/api/v1/sample-requests",
        method: "GET",
        params: status ? { status } : undefined,
      }),
  });
}

export function useSampleRequest(id: string | undefined) {
  return useQuery({
    queryKey: [...SAMPLE_REQUESTS_KEY, id],
    queryFn: () =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSampleRequestInput) =>
      customInstance<SampleRequest>({
        url: "/api/v1/sample-requests",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Sample request created");
    },
  });
}

export function useApproveSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, assigned_to }: { id: string; assigned_to?: string }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}/approve`,
        method: "POST",
        data: { assigned_to },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Request approved");
    },
  });
}

export function useRejectSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}/reject`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Request rejected");
    },
  });
}

export function useStartPreparingSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}/prepare`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Preparation started");
    },
  });
}

export function useFulfillSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, sample_id }: { id: string; sample_id: string }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}/fulfill`,
        method: "POST",
        data: { sample_id },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Request fulfilled");
    },
  });
}

export function useCancelSampleRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}/cancel`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Request cancelled");
    },
  });
}

export function useUpdateSampleRequest() {
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
    }) =>
      customInstance<SampleRequest>({
        url: `/api/v1/sample-requests/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAMPLE_REQUESTS_KEY });
      showSuccess("Request updated");
    },
  });
}
