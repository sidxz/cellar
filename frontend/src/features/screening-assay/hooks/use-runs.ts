"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateRunInput, Run } from "../types";

const RUNS_KEY = ["runs"];

export function useRunsByProtocol(protocolId: string | undefined) {
  return useQuery({
    queryKey: [...RUNS_KEY, "protocol", protocolId],
    queryFn: () =>
      customInstance<Run[]>({
        url: `/api/v1/protocols/${protocolId}/runs`,
        method: "GET",
      }),
    enabled: !!protocolId,
  });
}

export function useRun(id: string | undefined) {
  return useQuery({
    queryKey: [...RUNS_KEY, id],
    queryFn: () =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRunInput) =>
      customInstance<Run>({
        url: "/api/v1/runs",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/start`,
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useCompleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      plate_count,
      data_point_count,
    }: {
      id: string;
      plate_count: number;
      data_point_count: number;
    }) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/complete`,
        method: "POST",
        data: { plate_count, data_point_count },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useApproveRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/approve`,
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useRejectRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/reject`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useLockRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/lock`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useUnlockRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/unlock`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}

export function useUpdateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      data,
    }: {
      runId: string;
      data: {
        qc_metrics?: Record<string, unknown> | null;
        notes?: string | null;
      };
    }) =>
      customInstance<Run>({
        url: `/api/v1/runs/${runId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: RUNS_KEY }),
  });
}
