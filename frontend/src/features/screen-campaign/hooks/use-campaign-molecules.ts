import { useMemo } from "react";

import { useMoleculesByIds } from "@/features/chemical-registration";
import type { MoleculeResponse } from "@/shared/lib/api/model";

import type { CampaignResponse } from "../types";

/** The campaign's compounds by id: what the grid draws and what a search matches. One cached
 *  query, however many components ask. */
export function useCampaignMolecules(
  campaign: Pick<CampaignResponse, "results">,
): Map<string, MoleculeResponse> {
  const ids = useMemo(
    () => [...new Set((campaign.results ?? []).map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data } = useMoleculesByIds(ids);
  return useMemo(() => new Map((data?.items ?? []).map((m) => [m.id, m] as const)), [data]);
}
