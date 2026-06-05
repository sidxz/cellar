"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Protocol } from "../types";

const PROTOCOLS_KEY = ["protocols"];

export function useAddProtocolToProject(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/projects/${projectId}`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] });
      showSuccess("Protocol added to project");
    },
  });
}

export function useRemoveProtocolFromProject(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/projects/${projectId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] });
      showSuccess("Protocol removed from project");
    },
  });
}
