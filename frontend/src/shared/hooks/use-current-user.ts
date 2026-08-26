"use client";

import type { MeResponse } from "@/shared/lib/api/model";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

/**
 * Current user identity from `GET /api/v1/user/me`.
 *
 * Aliased from the orval-generated type.
 */
export type CurrentUser = MeResponse;

/** Current user identity (incl. org membership). Stable for the session. */
export function useCurrentUser() {
  return useQuery({
    queryKey: ["current-user"],
    queryFn: ({ signal }) =>
      customInstance<CurrentUser>({ url: "/api/v1/user/me", method: "GET", signal }),
    staleTime: Number.POSITIVE_INFINITY,
  });
}

/** Editors and admins may write (comments, records); viewers are read-only. */
export function canEdit(me: CurrentUser | undefined): boolean {
  return !!me && me.workspace_role !== "viewer";
}

/** {@link canEdit} bound to the current session's user, for components that
 * don't already have `me` in scope. */
export function useCanEdit(): boolean {
  const { data: me } = useCurrentUser();
  return canEdit(me);
}
