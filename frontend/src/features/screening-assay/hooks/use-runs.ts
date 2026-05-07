"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { CreateRunInput, Run } from "../types";

const RUNS_KEY = ["runs"];

const runHooks = createCrudHooks<Run, CreateRunInput, Record<string, unknown>>({
  entityName: "Run",
  baseUrl: "/api/v1/runs",
  queryKey: RUNS_KEY,
});

export const useRun = runHooks.useGet;
export const useCreateRun = runHooks.useCreate;

/** Custom list — runs are nested under protocols. */
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

// --- State transitions ---

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Run>({
        url: `/api/v1/runs/${id}/start`,
        method: "POST",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run started"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run completed"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run approved"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run rejected"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run locked"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run unlocked"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: RUNS_KEY }); showSuccess("Run updated"); },
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/runs/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run deleted");
    },
  });
}

interface RecomputeResponse {
  computed_readouts: number;
}

export interface RecomputeOverrides {
  override_top?: boolean;
  top_constraint?: number | null;
  top_constraint_min?: number | null;
  top_constraint_max?: number | null;
  override_bottom?: boolean;
  bottom_constraint?: number | null;
  bottom_constraint_min?: number | null;
  bottom_constraint_max?: number | null;
  override_hill?: boolean;
  hill_slope_constraint?:
    | "unconstrained"
    | "negative_only"
    | "positive_only"
    | "fixed_at_one"
    | null;
  hill_slope_min?: number | null;
  hill_slope_max?: number | null;
}

export interface RecomputeRunArgs {
  runId: string;
  overrides?: RecomputeOverrides;
}

export function useRecomputeRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, overrides }: RecomputeRunArgs) =>
      customInstance<RecomputeResponse>({
        url: `/api/v1/runs/${runId}/recompute`,
        method: "POST",
        ...(overrides ? { data: overrides } : {}),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["plate-map"] });
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["compound-curves"] });
      qc.invalidateQueries({ queryKey: ["protocol-activity"] });
      showSuccess(
        `Recomputed ${data.computed_readouts} readouts and refit curves`,
      );
    },
  });
}
