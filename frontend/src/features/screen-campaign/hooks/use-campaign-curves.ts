import { getCurvesBatchApiV1DoseResponseCurvesBatchPost } from "@/shared/lib/api/dose-response/dose-response";
import type { DoseResponseCurveResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import type { CampaignResponse } from "../types";

const CAMPAIGN_CURVES_KEY = ["campaign-curves"] as const;

/**
 * Batch-fetch all dose-response curves referenced by a campaign's measurements.
 * Returns a Map keyed by curve id. Empty Map for campaigns with no DR channels.
 *
 * NOTE: The cache invalidator that runs after a campaign refresh/recompute should
 * also invalidate this key (queryClient.invalidateQueries({ queryKey: ["campaign-curves", campaignId] }))
 * so stale curves are refetched for draft campaigns.
 */
export function useCampaignCurves(campaign: CampaignResponse | undefined) {
  const curveIds = collectCurveIds(campaign);
  const sortedKey = [...curveIds].sort().join(",");

  return useQuery({
    queryKey: [...CAMPAIGN_CURVES_KEY, campaign?.id ?? "", sortedKey],
    queryFn: async (): Promise<Map<string, DoseResponseCurveResponse>> => {
      if (curveIds.length === 0) return new Map();
      const resp = await getCurvesBatchApiV1DoseResponseCurvesBatchPost({
        curve_ids: curveIds,
      });
      return new Map(resp.curves.map((c) => [c.id, c] as const));
    },
    enabled: !!campaign && curveIds.length > 0,
    // staleTime omitted — inherits the global default (STALE_TIME.DEFAULT, 60s).
  });
}

function collectCurveIds(campaign: CampaignResponse | undefined): string[] {
  if (!campaign) return [];
  const ids = new Set<string>();
  for (const r of campaign.results ?? []) {
    for (const m of r.measurements ?? []) {
      if (m.source_curve_id) ids.add(m.source_curve_id);
    }
  }
  return [...ids];
}
