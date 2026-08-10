"use client";

import type { OrgDirectoryEntryResponse } from "@/shared/lib/api/model";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

/**
 * Sentinel org directory entry from `GET /api/v1/orgs`.
 *
 * Aliased from the orval-generated type.
 */
export type OrgDirectoryEntry = OrgDirectoryEntryResponse;

/** Org list for pickers/filters. Slow-moving — cached 5 minutes. */
export function useOrgs() {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: ({ signal }) =>
      customInstance<OrgDirectoryEntry[]>({ url: "/api/v1/orgs", method: "GET", signal }),
    staleTime: 5 * 60 * 1000,
  });
}
