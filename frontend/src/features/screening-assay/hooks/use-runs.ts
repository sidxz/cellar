"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RecomputeRunRequest, RecomputeRunResponse } from "@/shared/lib/api/model";
import { showSuccess, showWarning } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CreateRunInput, HitCriterion, Run } from "../types";
import {
  COMPOUND_CURVES_KEY,
  DOSE_RESPONSE_KEY,
  PLATE_MAP_KEY,
  PROTOCOL_ACTIVITY_KEY,
  READOUT_DATA_KEY,
  RUNS_KEY,
} from "./query-keys";

const runHooks = createCrudHooks<Run, CreateRunInput, Record<string, unknown>>({
  entityName: "Run",
  baseUrl: `${API_V1}/runs`,
  queryKey: RUNS_KEY,
});

export const useRun = runHooks.useGet;
export const useCreateRun = runHooks.useCreate;

/** Custom list — runs are nested under protocols. Supports optional tag filtering. */
export function useRunsByProtocol(
  protocolId: string | undefined,
  options?: { tags?: string[]; tagLogic?: "any" | "all" },
) {
  const tags = options?.tags?.length ? options.tags : null;
  return useQuery({
    queryKey: [
      ...RUNS_KEY,
      "protocol",
      protocolId,
      ...(tags ? [{ tags, tagLogic: options?.tagLogic ?? "any" }] : []),
    ],
    queryFn: () => {
      const params: Record<string, unknown> = {};
      if (tags) {
        params.tags = tags;
        params.tag_logic = options?.tagLogic ?? "any";
      }
      return customInstance<Run[]>({
        url: `${API_V1}/protocols/${protocolId}/runs`,
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
    },
    enabled: !!protocolId,
  });
}

// --- State transitions ---

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${id}/start`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run started");
    },
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
        url: `${API_V1}/runs/${id}/complete`,
        method: "POST",
        data: { plate_count, data_point_count },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run completed");
    },
  });
}

export function useApproveRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${id}/approve`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run approved");
    },
  });
}

export function useRejectRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${id}/reject`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run rejected");
    },
  });
}

export function useLockRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${id}/lock`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run locked");
    },
  });
}

export function useUnlockRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${id}/unlock`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run unlocked");
    },
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
        conditions?: Record<string, string> | null;
      };
    }) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${runId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run updated");
    },
  });
}

/** Record this run's hit criteria — an attributable per-run decision. An empty
 *  `criteria` array is a valid "show all, recorded" decision; to revert the run
 *  to "unset" (re-show the protocol recommendation) use `useResetRunHitCriteria`. */
export function useSetRunHitCriteria() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, criteria }: { runId: string; criteria: HitCriterion[] }) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${runId}/hit-criteria`,
        method: "PUT",
        data: { criteria },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Hit criteria saved for this run");
    },
  });
}

/** Clear this run's hit criteria, reverting to "unset" so the protocol
 *  recommendation is shown again as a suggestion. */
export function useResetRunHitCriteria() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      customInstance<Run>({
        url: `${API_V1}/runs/${runId}/hit-criteria`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Hit criteria reset to protocol recommendation");
    },
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `${API_V1}/runs/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      showSuccess("Run deleted");
    },
  });
}

// Aliases of the orval-generated recompute DTOs (request sent verbatim as the
// POST body; the generated HillSlopeConstraint enum carries the mode union).
type RecomputeResponse = RecomputeRunResponse;
export type RecomputeOverrides = RecomputeRunRequest;

export interface RecomputeRunArgs {
  runId: string;
  overrides?: RecomputeOverrides;
}

export function useRecomputeRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, overrides }: RecomputeRunArgs) =>
      customInstance<RecomputeResponse>({
        url: `${API_V1}/runs/${runId}/recompute`,
        method: "POST",
        ...(overrides ? { data: overrides } : {}),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: READOUT_DATA_KEY });
      qc.invalidateQueries({ queryKey: PLATE_MAP_KEY });
      qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY });
      qc.invalidateQueries({ queryKey: COMPOUND_CURVES_KEY });
      qc.invalidateQueries({ queryKey: PROTOCOL_ACTIVITY_KEY });
      showSuccess(`Recomputed ${data.computed_readouts} readouts and refit curves`);
      const warnings = data.fit_warnings ?? [];
      if (warnings.length > 0) {
        const head = warnings.slice(0, 3);
        const rest = warnings.length - head.length;
        const description = rest > 0 ? `${head.join("\n")}\n+${rest} more` : head.join("\n");
        showWarning(`${warnings.length} curve(s) had fit issues — see the chart for details.`, {
          description,
        });
      }
    },
  });
}
