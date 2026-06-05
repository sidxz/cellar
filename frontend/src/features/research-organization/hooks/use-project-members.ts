"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AddMemberInput, ProjectMember } from "../types";

const membersKey = (projectId: string) => ["projects", projectId, "members"];

export function useProjectMembers(projectId: string | undefined) {
  return useQuery({
    queryKey: membersKey(projectId!),
    queryFn: () =>
      customInstance<ProjectMember[]>({
        url: `/api/v1/projects/${projectId}/members`,
        method: "GET",
      }),
    enabled: !!projectId,
  });
}

export function useAddProjectMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AddMemberInput) =>
      customInstance<ProjectMember>({
        url: `/api/v1/projects/${projectId}/members`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: membersKey(projectId) });
      showSuccess("Member added");
    },
  });
}

export function useUpdateMemberRole(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      customInstance<ProjectMember>({
        url: `/api/v1/projects/${projectId}/members/${userId}`,
        method: "PATCH",
        data: { role },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: membersKey(projectId) });
      showSuccess("Role updated");
    },
  });
}

export function useRemoveProjectMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      customInstance({
        url: `/api/v1/projects/${projectId}/members/${userId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: membersKey(projectId) });
      showSuccess("Member removed");
    },
  });
}
