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
