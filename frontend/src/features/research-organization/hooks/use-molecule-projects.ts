"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { MOLECULES_KEY } from "@/features/chemical-registration/hooks/query-keys";

const moleculeProjectsKey = (moleculeId: string) => [...MOLECULES_KEY, moleculeId, "projects"];

export function useMoleculeProjects(moleculeId: string | undefined) {
  return useQuery({
    queryKey: moleculeProjectsKey(moleculeId!),
    queryFn: () =>
      customInstance<string[]>({
        url: `/api/v1/molecules/${moleculeId}/projects`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

export function useAddMoleculeToProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (moleculeId: string) =>
      customInstance({
        url: `/api/v1/projects/${projectId}/molecules/${moleculeId}`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Compound added to project");
    },
  });
}

export function useRemoveMoleculeFromProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (moleculeId: string) =>
      customInstance({
        url: `/api/v1/projects/${projectId}/molecules/${moleculeId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Compound removed from project");
    },
  });
}
