"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";

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
        url: "/api/v1/user/workspace-members",
        method: "GET",
        params: q ? { q } : undefined,
      }),
  });
}
