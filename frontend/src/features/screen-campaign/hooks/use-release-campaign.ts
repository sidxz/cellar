import { useMutation, useQueryClient } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { CampaignResponse, ReleaseCampaignRequest } from "@/shared/lib/api/model";
import { campaignKeys } from "./use-campaigns";

/** A workspace admin gives a campaign another app manages back to ChemCellar, with a reason.
 *  POST /campaigns/{id}/release { reason } → the campaign, no longer managed. */
export function useReleaseCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ campaignId, reason }: { campaignId: string } & ReleaseCampaignRequest) =>
      customInstance<CampaignResponse>({
        url: `${API_V1}/campaigns/${campaignId}/release`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: (_campaign, { campaignId }) =>
      qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) }),
  });
}
