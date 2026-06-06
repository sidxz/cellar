"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Protocol } from "../types";
import { PROTOCOLS_KEY } from "./query-keys";

/**
 * Assign a freshly-created protocol to a project.
 *
 * Unlike {@link useAddProtocolToProject}, the protocol id is not known at hook
 * construction time (the protocol is created first), so both ids are passed at
 * call time. This variant is for the create-protocol flow where the create
 * mutation already toasts success — so success here is silent (only the cache
 * is invalidated), while a failed assignment surfaces a recovery hint instead
 * of vanishing. Invalidating the root protocols key refetches every
 * project-scoped protocol list (keyed `["protocols", { projectId }]`).
 */
export function useAssignProtocolToProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ protocolId, projectId }: { protocolId: string; projectId: string }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/projects/${projectId}`,
        method: "POST",
      }),
    onSuccess: (_data, { protocolId }) => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: [...PROTOCOLS_KEY, protocolId] });
    },
    onError: () => {
      showError(
        "Protocol created but could not be added to the project — add it manually from the project page.",
      );
    },
  });
}

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
