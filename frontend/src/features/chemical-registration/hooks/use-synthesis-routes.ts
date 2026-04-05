"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  AddReactionStepInput,
  CreateSynthesisRouteInput,
  RecordStepOutcomeInput,
  SynthesisRoute,
  SynthesisRouteSummary,
} from "../types/synthesis-route";

const SYNTHESIS_ROUTES_KEY = ["synthesis-routes"];

export function useSynthesisRoutesByMolecule(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...SYNTHESIS_ROUTES_KEY, "molecule", moleculeId],
    queryFn: () =>
      customInstance<SynthesisRouteSummary[]>({
        url: "/api/v1/synthesis-routes",
        method: "GET",
        params: { molecule_id: moleculeId as string },
      }),
    enabled: !!moleculeId,
  });
}

export function useSynthesisRoute(id: string | undefined) {
  return useQuery({
    queryKey: [...SYNTHESIS_ROUTES_KEY, id],
    queryFn: () =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateSynthesisRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSynthesisRouteInput) =>
      customInstance<SynthesisRoute>({
        url: "/api/v1/synthesis-routes",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Synthesis route created");
    },
  });
}

export function useAddReactionStep(routeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AddReactionStepInput) =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${routeId}/steps`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Reaction step added");
    },
  });
}

export function useRecordStepOutcome(routeId: string, stepId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RecordStepOutcomeInput) =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${routeId}/steps/${stepId}/outcome`,
        method: "PUT",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Step outcome recorded");
    },
  });
}

export function useValidateSynthesisRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${id}/validate`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Synthesis route validated");
    },
  });
}

export function useSetPreferredRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${id}/prefer`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Synthesis route set as preferred");
    },
  });
}

export function useDeprecateSynthesisRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string | null }) =>
      customInstance<SynthesisRoute>({
        url: `/api/v1/synthesis-routes/${id}/deprecate`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNTHESIS_ROUTES_KEY });
      showSuccess("Synthesis route deprecated");
    },
  });
}
