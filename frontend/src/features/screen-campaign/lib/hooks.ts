/**
 * TanStack Query wrappers for the screen-campaign feature.
 *
 * Each hook provides a project-id or campaign-id scoped query with a
 * stable, feature-owned queryKey — callers never need to construct keys
 * or import from the generated path directly.
 *
 * Mutation wrappers are intentionally deferred to Phase 8.
 */
import { useQuery } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";

import {
  listCampaignsApiV1CampaignsGet,
  getCampaignApiV1CampaignsCampaignIdGet,
} from "@/shared/lib/api/campaigns/campaigns";
import { listMoleculesApiV1MoleculesGet } from "@/shared/lib/api/molecules/molecules";
import type { CampaignResponse } from "@/shared/lib/api/model";

// ─── Query key factory ───────────────────────────────────────────────────────

export const campaignKeys = {
  all: ["campaigns"] as const,
  byProject: (projectId: string) =>
    ["campaigns", "by-project", projectId] as const,
  detail: (campaignId: string) => ["campaigns", campaignId] as const,
} as const;

// ─── List hook ───────────────────────────────────────────────────────────────

/**
 * Fetches all campaigns for the given project (workspace-scoped automatically
 * by the auth middleware on the backend).
 */
export function useCampaignsByProject(
  projectId: string,
  options?: Partial<
    UseQueryOptions<CampaignResponse[], Error, CampaignResponse[]>
  >,
) {
  return useQuery({
    queryKey: campaignKeys.byProject(projectId),
    queryFn: () =>
      listCampaignsApiV1CampaignsGet({ project_id: projectId }),
    enabled: !!projectId,
    ...options,
  });
}

// ─── Detail hook ─────────────────────────────────────────────────────────────

/**
 * Fetches a single campaign by id (full draft view: channels + results).
 */
export function useCampaign(
  campaignId: string,
  options?: Partial<
    UseQueryOptions<CampaignResponse, Error, CampaignResponse>
  >,
) {
  return useQuery({
    queryKey: campaignKeys.detail(campaignId),
    queryFn: () => getCampaignApiV1CampaignsCampaignIdGet(campaignId),
    enabled: !!campaignId,
    ...options,
  });
}

// ─── Bulk molecule lookup hook ───────────────────────────────────────────────

/**
 * Bulk-fetches molecules by id list (workspace-scoped).
 * Uses GET /api/v1/molecules?ids=<csv>.
 * The query key is stable for the same sorted id set.
 */
export function useMoleculesByIds(ids: string[]) {
  const sortedKey = [...ids].sort().join(",");
  return useQuery({
    queryKey: ["molecules", "by-ids", sortedKey],
    queryFn: () => listMoleculesApiV1MoleculesGet({ ids: sortedKey }),
    enabled: ids.length > 0,
  });
}
