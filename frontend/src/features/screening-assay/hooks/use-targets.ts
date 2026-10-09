"use client";

import { WORKSPACE_SETUP_KEY } from "@/features/workspace-config/hooks/use-workspace-setup";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RequestTargetBody } from "@/shared/lib/api/model";
import type { PaginatedResponse } from "@/shared/types/pagination";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Target, TargetSyncReport } from "../types";

export const TARGETS_KEY = ["targets"];

/** Every target in the mirror. Pickers must see the whole catalog, so this
 *  follows the cursor to the end instead of taking the server's default page. */
async function fetchAllTargets(): Promise<Target[]> {
  const items: Target[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < 50; page++) {
    const result: PaginatedResponse<Target> = await customInstance({
      url: `${API_V1}/targets`,
      method: "GET",
      params: { limit: 200, ...(cursor ? { cursor } : {}) },
    });
    items.push(...result.items);
    cursor = result.next_cursor;
    if (!cursor) return items;
  }
  throw new Error("targets: cursor pagination did not terminate after 50 pages");
}

export function useTargets() {
  return useQuery({ queryKey: TARGETS_KEY, queryFn: fetchAllTargets });
}

/** Admin-only full sync from prot-cellar. Errors carry the backend message
 *  (e.g. "prot-cellar refused … requires the editor role"). */
export function useSyncTargets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customInstance<TargetSyncReport>({ url: `${API_V1}/targets/sync`, method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TARGETS_KEY });
      qc.invalidateQueries({ queryKey: WORKSPACE_SETUP_KEY });
    },
  });
}

/** Editor: create a missing target in ProtCellar (with the caller's tokens) and mirror it.
 *  The new target joins the cached list at once so the picker can show it as selected. */
export function useRequestTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RequestTargetBody) =>
      customInstance<Target>({ url: `${API_V1}/targets/request`, method: "POST", data }),
    onSuccess: (target) => {
      qc.setQueryData<Target[]>(TARGETS_KEY, (old) => (old ? [...old, target] : old));
      qc.invalidateQueries({ queryKey: TARGETS_KEY });
    },
  });
}
