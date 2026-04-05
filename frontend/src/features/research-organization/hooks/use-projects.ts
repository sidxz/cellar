"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { CreateProjectInput, Project, UpdateProjectInput } from "../types";

const PROJECTS_KEY = ["projects"];

export function useProjects() {
  return useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () =>
      customInstance<Project[]>({
        url: "/api/v1/projects",
        method: "GET",
      }),
  });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: [...PROJECTS_KEY, id],
    queryFn: () =>
      customInstance<Project>({
        url: `/api/v1/projects/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateProjectInput) =>
      customInstance<Project>({
        url: "/api/v1/projects",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_KEY });
      showSuccess("Project created");
    },
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateProjectInput) =>
      customInstance<Project>({
        url: `/api/v1/projects/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_KEY });
      showSuccess("Project updated");
    },
  });
}

export function useArchiveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Project>({
        url: `/api/v1/projects/${id}/archive`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_KEY });
      showSuccess("Project archived");
    },
  });
}
