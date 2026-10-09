"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { WorkspaceSetupResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

/** Every mutation that can complete a checklist item invalidates this key. */
export const WORKSPACE_SETUP_KEY = ["workspace-setup"];

export type WorkspaceSetup = WorkspaceSetupResponse;

export function useWorkspaceSetup(enabled: boolean) {
  return useQuery({
    queryKey: WORKSPACE_SETUP_KEY,
    queryFn: () =>
      customInstance<WorkspaceSetup>({ url: `${API_V1}/workspace-setup`, method: "GET" }),
    enabled,
  });
}
