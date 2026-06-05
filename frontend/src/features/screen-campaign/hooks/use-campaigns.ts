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

import { getCampaignApiV1CampaignsCampaignIdGet } from "@/shared/lib/api/campaigns/campaigns";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CampaignResponse, PaginatedResponseCampaignResponse } from "@/shared/lib/api/model";

// ─── Query key factory ───────────────────────────────────────────────────────

export const campaignKeys = {
  all: ["campaigns"] as const,
  byProject: (projectId: string) => ["campaigns", "by-project", projectId] as const,
  detail: (campaignId: string) => ["campaigns", campaignId] as const,
} as const;

// ─── List hook ───────────────────────────────────────────────────────────────

/**
 * Fetches all campaigns, optionally filtered to a given project and/or tags.
 * If `projectId` is provided the query is workspace-scoped to that project
 * by the auth middleware on the backend.
 * `tags` + `tagLogic` filter campaigns by assigned tags (passed to the
 * backend `tags` / `tag_logic` query params).
 */
export function useCampaigns(
  projectId?: string,
  options?: {
    tags?: string[];
    tagLogic?: "any" | "all";
  } & Partial<UseQueryOptions<CampaignResponse[], Error, CampaignResponse[]>>,
) {
  const { tags: rawTags, tagLogic, ...queryOptions } = options ?? {};
  const tags = rawTags?.length ? rawTags : null;

  const queryKey = projectId
    ? tags
      ? [...campaignKeys.byProject(projectId), { tags, tagLogic: tagLogic ?? "any" }]
      : campaignKeys.byProject(projectId)
    : tags
      ? [...campaignKeys.all, { tags, tagLogic: tagLogic ?? "any" }]
      : campaignKeys.all;

  return useQuery({
    queryKey,
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (projectId) params.project_id = projectId;
      if (tags) {
        params.tags = tags;
        params.tag_logic = tagLogic ?? "any";
      }
      const page = await customInstance<PaginatedResponseCampaignResponse>({
        url: "/api/v1/campaigns",
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
      return page.items;
    },
    enabled: projectId !== undefined ? !!projectId : true,
    ...queryOptions,
  });
}

// ─── Detail hook ─────────────────────────────────────────────────────────────

/**
 * Fetches a single campaign by id (full draft view: channels + results).
 */
export function useCampaign(
  campaignId: string,
  options?: Partial<UseQueryOptions<CampaignResponse, Error, CampaignResponse>>,
) {
  return useQuery({
    queryKey: campaignKeys.detail(campaignId),
    queryFn: () => getCampaignApiV1CampaignsCampaignIdGet(campaignId),
    enabled: !!campaignId,
    ...options,
  });
}
