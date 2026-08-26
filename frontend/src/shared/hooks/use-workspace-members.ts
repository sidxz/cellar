"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

export interface WorkspaceMember {
  user_id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  role: string;
}

const MEMBERS_KEY = ["workspace-members"];

export function useWorkspaceMembers(q?: string) {
  return useQuery({
    queryKey: [...MEMBERS_KEY, q],
    queryFn: () =>
      customInstance<WorkspaceMember[]>({
        url: `${API_V1}/user/workspace-members`,
        method: "GET",
        params: q ? { q } : undefined,
      }),
  });
}

/** user_id → display name over the full member list. "" for null, "…" while
 * loading, "Unknown member" when the list is loaded but has no such id. */
export function useMemberNames(): (userId: string | null | undefined) => string {
  const { data } = useWorkspaceMembers();
  const byId = useMemo(() => new Map((data ?? []).map((m) => [m.user_id, m.name])), [data]);
  return useCallback(
    (userId) => {
      if (!userId) return "";
      if (!data) return "…";
      return byId.get(userId) ?? "Unknown member";
    },
    [byId, data],
  );
}
