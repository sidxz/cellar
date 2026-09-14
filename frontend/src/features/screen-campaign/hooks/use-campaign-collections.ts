"use client";

import { createLinkHooks } from "@/features/screening-assay/hooks/create-link-hooks";
import type { CollectionCoverage } from "@/features/screening-assay/types";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { campaignKeys } from "./use-campaigns";

const coverageKey = (campaignId: string) => [...campaignKeys.detail(campaignId), "collections"];

const campaignCollectionHooks = createLinkHooks({
  entitySegment: "campaigns",
  linkSegment: "collections",
  labels: { addedTo: "Library added to campaign", removedFrom: "Library removed from campaign" },
  // Only the coverage read changes — the campaign itself carries no libraries,
  // so its detail query needn't refetch (it drags results + measurements).
  invalidateKeys: (campaignId) => [coverageKey(campaignId)],
});

/** One invalidation pass after a library gesture (single toggle or a batched diff). */
export const invalidateCampaignCollectionQueries = campaignCollectionHooks.invalidateTargetQueries;

/** Link a library to a campaign (idempotent server-side). 409 once the campaign
 *  is closed; 404 for an unknown library. Invalidation is the CALLER's job via
 *  `invalidateCampaignCollectionQueries` — batched diffs invalidate once. */
export const useAddCampaignCollection = campaignCollectionHooks.useAddTarget;

/** Unlink a library from a campaign. */
export const useRemoveCampaignCollection = campaignCollectionHooks.useRemoveTarget;

/** Per linked library: members read in any of the campaign's seed runs. */
export function useCampaignCollectionCoverage(campaignId: string) {
  return useQuery({
    queryKey: coverageKey(campaignId),
    queryFn: () =>
      customInstance<CollectionCoverage[]>({
        url: `${API_V1}/campaigns/${campaignId}/collection-coverage`,
        method: "GET",
      }),
    enabled: Boolean(campaignId),
  });
}
