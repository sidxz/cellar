"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { WorkspaceSettings } from "../types";

const SETTINGS_KEY = ["workspace-settings"];

export function useWorkspaceSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: () =>
      customInstance<WorkspaceSettings>({
        url: "/api/v1/settings",
        method: "GET",
      }),
  });
}

export function useUpdateWorkspaceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<WorkspaceSettings>) =>
      customInstance<WorkspaceSettings>({
        url: "/api/v1/settings",
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEY }),
  });
}
