"use client";

import { createLinkHooks } from "@/features/screening-assay/hooks/create-link-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { CampaignCollectionCoverageResponse } from "../types";
import { campaignKeys } from "./use-campaigns";

const coverageKey = (campaignId: string, withStages: boolean) => [
  ...campaignKeys.detail(campaignId),
  "collections",
  ...(withStages ? ["stages"] : []),
];

const campaignCollectionHooks = createLinkHooks({
  entitySegment: "campaigns",
  linkSegment: "collections",
  labels: { addedTo: "Library added to campaign", removedFrom: "Library removed from campaign" },
  // Only the coverage read changes — the campaign itself carries no libraries,
  // so its detail query needn't refetch (it drags results + measurements).
  // Both the plain and the with-stages read, since a link changes both.
  invalidateKeys: (campaignId) => [[...campaignKeys.detail(campaignId), "collections"]],
});

/** One invalidation pass after a library gesture (single toggle or a batched diff). */
export const invalidateCampaignCollectionQueries = campaignCollectionHooks.invalidateTargetQueries;

/** Link a library to a campaign (idempotent server-side). 409 once the campaign
 *  is closed; 404 for an unknown library. Invalidation is the CALLER's job via
 *  `invalidateCampaignCollectionQueries` — batched diffs invalidate once. */
export const useAddCampaignCollection = campaignCollectionHooks.useAddTarget;

/** Unlink a library from a campaign. */
export const useRemoveCampaignCollection = campaignCollectionHooks.useRemoveTarget;

/** Per linked library: members read in any of the campaign's seed runs.
 *
 *  `withStages` also asks for each library's rows tallied through the
 *  campaign's stages (`?include=stages`). That costs the backend a full
 *  campaign load, so it is opt-in — leave it off where only the bars show. */
export function useCampaignCollectionCoverage(campaignId: string, withStages = false) {
  return useQuery({
    queryKey: coverageKey(campaignId, withStages),
    queryFn: () =>
      customInstance<CampaignCollectionCoverageResponse[]>({
        url: `${API_V1}/campaigns/${campaignId}/collection-coverage`,
        method: "GET",
        ...(withStages ? { params: { include: "stages" } } : {}),
      }),
    enabled: Boolean(campaignId),
  });
}
