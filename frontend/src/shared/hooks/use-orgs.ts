"use client";

import type { OrgDirectoryEntryResponse } from "@/shared/lib/api/model";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

/**
 * Duar org directory entry from `GET /api/v1/orgs`.
 *
 * Aliased from the orval-generated type.
 */
export type OrgDirectoryEntry = OrgDirectoryEntryResponse;

/** Org list for pickers/filters (enabled orgs). `includeDisabled` adds disabled ones,
 * for naming a record whose org was disabled since. Slow-moving — cached 5 minutes. */
export function useOrgs({ includeDisabled = false }: { includeDisabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["orgs", includeDisabled],
    queryFn: ({ signal }) =>
      customInstance<OrgDirectoryEntry[]>({
        url: "/api/v1/orgs",
        method: "GET",
        params: includeDisabled ? { include_disabled: true } : undefined,
        signal,
      }),
    staleTime: 5 * 60 * 1000,
  });
}

/** Duar org id → name, disabled orgs included. "" for null, "…" while loading,
 * "Unknown org" when the list is loaded but has no such id. */
export function useOrgName(): (orgId: string | null | undefined) => string {
  const { data } = useOrgs({ includeDisabled: true });
  const byId = useMemo(() => new Map((data ?? []).map((o) => [o.id, o.name])), [data]);
  return useCallback(
    (orgId) => {
      if (!orgId) return "";
      if (!data) return "…";
      return byId.get(orgId) ?? "Unknown org";
    },
    [byId, data],
  );
}
