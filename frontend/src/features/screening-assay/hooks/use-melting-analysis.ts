"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  AddMeltingStepRequest,
  AssignMeltingStepRequest,
  ReviewMeltingStepRequest,
} from "@/shared/lib/api/model";
import type { MeltingAnalysis, MeltingStepChange } from "../types";
import { MELTING_ANALYSIS_KEY, READOUT_DATA_KEY } from "./query-keys";

/** A run's melting steps and its temperature windows' results. */
export function useMeltingAnalysis(runId: string) {
  return useQuery({
    queryKey: [...MELTING_ANALYSIS_KEY, runId],
    queryFn: () =>
      customInstance<MeltingAnalysis>({
        url: `${API_V1}/runs/${runId}/melting-analysis`,
        method: "GET",
      }),
  });
}

/** A step change recalculates the run's Tm and ΔTm rows. */
function useInvalidateAfterStepChange(runId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: [...MELTING_ANALYSIS_KEY, runId] });
    qc.invalidateQueries({ queryKey: READOUT_DATA_KEY });
  };
}

/** POST /api/v1/runs/{runId}/melting-steps: a step added by hand. The step
 *  returned joins the cached analysis at once, so what names it (a pick on the
 *  plot) need not wait; the read that follows brings the results. */
export function useAddMeltingStep(runId: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateAfterStepChange(runId);
  return useMutation({
    mutationFn: (body: AddMeltingStepRequest) =>
      customInstance<MeltingStepChange>({
        url: `${API_V1}/runs/${runId}/melting-steps`,
        method: "POST",
        data: body,
      }),
    onSuccess: ({ step }) => {
      qc.setQueryData<MeltingAnalysis>(
        [...MELTING_ANALYSIS_KEY, runId],
        (a) => a && { ...a, steps: [...a.steps.filter((s) => s.id !== step.id), step] },
      );
      invalidate();
    },
  });
}

/** PATCH /api/v1/melting-steps/{stepId} with the step's full desired state. A
 *  409 means the step changed since it was loaded, or the run no longer allows edits. */
export function useReviewMeltingStep(runId: string) {
  const onSuccess = useInvalidateAfterStepChange(runId);
  return useMutation({
    mutationFn: ({ stepId, body }: { stepId: string; body: ReviewMeltingStepRequest }) =>
      customInstance<MeltingStepChange>({
        url: `${API_V1}/melting-steps/${stepId}`,
        method: "PATCH",
        data: body,
      }),
    onSuccess,
  });
}

/** PUT /api/v1/melting-steps/{stepId}/assignment: the window the step is
 *  assigned to for its position; a null window clears the assignment. A 409
 *  means the step changed since it was loaded, or the run no longer allows edits. */
export function useAssignMeltingStep(runId: string) {
  const onSuccess = useInvalidateAfterStepChange(runId);
  return useMutation({
    mutationFn: ({ stepId, body }: { stepId: string; body: AssignMeltingStepRequest }) =>
      customInstance<MeltingStepChange>({
        url: `${API_V1}/melting-steps/${stepId}/assignment`,
        method: "PUT",
        data: body,
      }),
    onSuccess,
  });
}
