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
  getCampaignApiV1CampaignsCampaignIdGet,
  getCampaignSummaryApiV1CampaignsCampaignIdSummaryGet,
} from "@/shared/lib/api/campaigns/campaigns";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CampaignResponse,
  CampaignSummaryResponse,
  ListCampaignsApiV1CampaignsGetParams,
  PaginatedResponseCampaignSummaryResponse,
} from "@/shared/lib/api/model";

/** The lifecycle states the list endpoint can be narrowed to. */
export type CampaignStatusFilter = NonNullable<ListCampaignsApiV1CampaignsGetParams["status"]>;

// ─── Query key factory ───────────────────────────────────────────────────────

export const campaignKeys = {
  all: ["campaigns"] as const,
  byProject: (projectId: string) => ["campaigns", "by-project", projectId] as const,
  detail: (campaignId: string) => ["campaigns", campaignId] as const,
  summary: (campaignId: string) => ["campaigns", campaignId, "summary"] as const,
} as const;

// ─── List hook ───────────────────────────────────────────────────────────────

/**
 * Fetches all campaigns, optionally filtered to a given project and/or tags.
 * If `projectId` is provided the query is workspace-scoped to that project
 * by the auth middleware on the backend.
 * `tags` + `tagLogic` filter campaigns by assigned tags (passed to the
 * backend `tags` / `tag_logic` query params); `status` narrows to one
 * lifecycle state.
 *
 * Items are summaries — every campaign field except the result rows, plus
 * `result_count` and stage `counts`.
 */
export function useCampaigns(
  projectId?: string,
  options?: {
    tags?: string[];
    tagLogic?: "any" | "all";
    targets?: string[];
    targetLogic?: "any" | "all";
    status?: CampaignStatusFilter;
  } & Partial<UseQueryOptions<CampaignSummaryResponse[], Error, CampaignSummaryResponse[]>>,
) {
  const {
    tags: rawTags,
    tagLogic,
    targets: rawTargets,
    targetLogic,
    status,
    ...queryOptions
  } = options ?? {};
  const tags = rawTags?.length ? rawTags : null;
  const targets = rawTargets?.length ? rawTargets : null;

  const filterKey =
    tags || targets || status
      ? {
          tags,
          tagLogic: tagLogic ?? "any",
          targets,
          targetLogic: targetLogic ?? "any",
          status: status ?? null,
        }
      : null;
  const baseKey = projectId ? campaignKeys.byProject(projectId) : campaignKeys.all;
  const queryKey = filterKey ? [...baseKey, filterKey] : baseKey;

  return useQuery({
    queryKey,
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (projectId) params.project_id = projectId;
      if (tags) {
        params.tags = tags;
        params.tag_logic = tagLogic ?? "any";
      }
      if (targets) {
        params.targets = targets;
        params.target_logic = targetLogic ?? "any";
      }
      if (status) params.status = status;
      const page = await customInstance<PaginatedResponseCampaignSummaryResponse>({
        url: `${API_V1}/campaigns`,
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

// ─── Summary hook ────────────────────────────────────────────────────────────

/**
 * Fetches a campaign without its result rows — stages (with their funnel
 * counts) and channels, plus `result_count`. Use it wherever the rows aren't
 * rendered; `useCampaign` is the full draft view.
 */
export function useCampaignSummary(
  campaignId: string,
  options?: Partial<UseQueryOptions<CampaignSummaryResponse, Error, CampaignSummaryResponse>>,
) {
  return useQuery({
    queryKey: campaignKeys.summary(campaignId),
    queryFn: () => getCampaignSummaryApiV1CampaignsCampaignIdSummaryGet(campaignId),
    enabled: !!campaignId,
    ...options,
  });
}
