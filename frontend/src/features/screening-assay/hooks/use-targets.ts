"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { PaginatedResponse } from "@/shared/types/pagination";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Target, TargetSyncReport } from "../types";

export const TARGETS_KEY = ["targets"];

/** Every target in the mirror. Pickers must see the whole catalog, so this
 *  follows the cursor to the end instead of taking the server's default page. */
async function fetchAllTargets(): Promise<Target[]> {
  const items: Target[] = [];
  let cursor: string | null = null;
  do {
    const page: PaginatedResponse<Target> = await customInstance({
      url: `${API_V1}/targets`,
      method: "GET",
      params: { limit: 200, ...(cursor ? { cursor } : {}) },
    });
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
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
    },
  });
}
