/**
 * One stable color per protocol in a campaign, so a protocol reads the same
 * hue on readout chips, stage criteria, and the results-grid column group.
 * Assigned by first appearance in channel display order (not hashed —
 * hashing two protocols to the same palette slot would defeat the point).
 */

import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { CampaignChannelResponse } from "../types";

export function protocolColorById(
  channels: Pick<CampaignChannelResponse, "protocol_id" | "display_order">[],
): Map<string, string> {
  const map = new Map<string, string>();
  for (const ch of [...channels].sort((a, b) => a.display_order - b.display_order)) {
    if (!map.has(ch.protocol_id)) {
      map.set(ch.protocol_id, GROUP_PALETTE[map.size % GROUP_PALETTE.length]);
    }
  }
  return map;
}
