"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

/**
 * Build identity reported by the backend `/version` endpoint.
 *
 * Prefer the orval-generated `VersionResponse` once `pnpm generate:api` has
 * run; this local shape is the same contract for environments where the type
 * has not yet been generated.
 */
export interface ApiVersionResponse {
  name: string;
  version: string;
  git_sha: string;
  build_date: string;
  environment: string;
}

/** Fetch the backend build identity. `/version` is a root path (not /api/v1). */
export function useApiVersion(enabled: boolean) {
  return useQuery({
    queryKey: ["api-version"],
    queryFn: ({ signal }) =>
      customInstance<ApiVersionResponse>({ url: "/version", method: "GET", signal }),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
}
