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
 * Fetches all campaigns, optionally filtered to a given project.
 * If `projectId` is provided the query is workspace-scoped to that project
 * by the auth middleware on the backend.
 */
export function useCampaigns(
  projectId?: string,
  options?: Partial<
    UseQueryOptions<CampaignResponse[], Error, CampaignResponse[]>
  >,
) {
  return useQuery({
    queryKey: projectId ? campaignKeys.byProject(projectId) : campaignKeys.all,
    queryFn: async () => {
      const page = await listCampaignsApiV1CampaignsGet(
        projectId ? { project_id: projectId } : {},
      );
      return page.items;
    },
    enabled: projectId !== undefined ? !!projectId : true,
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
