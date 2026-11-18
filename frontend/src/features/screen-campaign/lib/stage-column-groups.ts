/**
 * Columns grouped by the stage that owns them, in funnel order — the order the
 * results grid, the readouts section and every stage picker share.
 */

import type { CampaignChannelResponse, CampaignStageResponse } from "../types";

/** Title of the group holding campaign columns (no stage judges them). */
export const OTHER_COLUMNS = "Other columns";

export interface StageColumnGroup {
  /** null for campaign columns. */
  stageId: string | null;
  title: string;
  channels: CampaignChannelResponse[];
}

type StageLike = Pick<CampaignStageResponse, "id" | "parent_stage_id" | "display_order">;

/** Parents before children: each root, then its children (recursively), with
 *  roots and siblings by display_order. A stage whose parent is gone counts as
 *  a root. */
export function stagesInFunnelOrder<S extends StageLike>(stages: S[]): S[] {
  const byOrder = [...stages].sort((a, b) => a.display_order - b.display_order);
  const ids = new Set(stages.map((s) => s.id));
  const out: S[] = [];
  const seen = new Set<string>();
  const visit = (s: S) => {
    if (seen.has(s.id)) return;
    seen.add(s.id);
    out.push(s);
    for (const child of byOrder) if (child.parent_stage_id === s.id) visit(child);
  };
  for (const s of byOrder) if (!s.parent_stage_id || !ids.has(s.parent_stage_id)) visit(s);
  for (const s of byOrder) visit(s); // a parent cycle the server never sends
  return out;
}

/** Stage groups in funnel order, then campaign columns under "Other columns".
 *  Columns keep display_order within a group; a stage with no columns is left
 *  out. */
export function groupColumnsByStage(
  channels: CampaignChannelResponse[],
  stages: CampaignStageResponse[],
): StageColumnGroup[] {
  const sorted = [...channels].sort((a, b) => a.display_order - b.display_order);
  const known = new Set(stages.map((s) => s.id));
  const groups: StageColumnGroup[] = stagesInFunnelOrder(stages).map((s) => ({
    stageId: s.id,
    title: s.name,
    channels: sorted.filter((c) => c.stage_id === s.id),
  }));
  groups.push({
    stageId: null,
    title: OTHER_COLUMNS,
    channels: sorted.filter((c) => !c.stage_id || !known.has(c.stage_id)),
  });
  return groups.filter((g) => g.channels.length > 0);
}
