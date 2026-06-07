"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

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
