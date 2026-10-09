"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  NamingChangePreviewResponse,
  NamingChangeRequest,
  SetHomeOrganismRequest,
  WorkspaceSettingsResponse,
} from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

/** What an admin naming edit would rename, before it is saved. */
export function usePreviewNamingChange() {
  return useMutation({
    mutationFn: (data: NamingChangeRequest) =>
      customInstance<NamingChangePreviewResponse>({
        url: `${API_V1}/protocol-names/preview-change`,
        method: "POST",
        data,
      }),
    onError: (err: Error) => showError(err.message),
  });
}

/** Set (or clear) the home organism; relabels protocols. */
export function useSetHomeOrganism() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SetHomeOrganismRequest) =>
      customInstance<WorkspaceSettingsResponse>({
        url: `${API_V1}/settings/home-organism`,
        method: "PUT",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspace-settings"] });
      qc.invalidateQueries({ queryKey: ["protocols"] });
      showSuccess("Home organism saved");
    },
    onError: (err: Error) => showError(err.message),
  });
}
