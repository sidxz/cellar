/**
 * Cluster palette dispatcher — color per point given current color mode + paint inputs.
 *
 * Helpers used:
 *   - GROUP_PALETTE from @/shared/lib/chart-colors  (exists — 12-color cycle)
 *   - classifyActivity from ./scaffold-rollup        (exists — pIC50 → 4-bin)
 *
 * Missing helpers (no activityColorForPic50 / scaffoldColorForBucket found in the codebase):
 *   - Activity mode uses a local 4-bin color map aligned with the scaffold-rollup bins.
 *   - Scaffold mode uses GROUP_PALETTE keyed by scaffoldId hash; falls back to MUTED_GREY
 *     when scaffoldId is null.
 */

import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { type ActivityRollupBin, classifyActivity } from "./scaffold-rollup";

export type ColorOption =
  | { mode: "cluster" }
  | { mode: "activity"; protocolId: string }
  | { mode: "scaffold" }
  | { mode: "none" };

export interface PointPaint {
  clusterId: number;
  activityPic50: number | null;
  scaffoldId: string | null;
}

const MUTED_GREY = "#a1a1aa";

/**
 * Activity bin colors (chemist convention, matching scaffold-rollup thresholds):
 *   active_high  pIC50 >= 8  → emerald
 *   active_mid   pIC50 >= 6  → orange
 *   weak         pIC50 >= 5  → amber
 *   inactive     pIC50 <  5  → red
 *
 * Note: activityColorForPic50 does not exist in the codebase; these bins are
 * derived inline to match the scaffold-rollup classification already in use.
 */
const ACTIVITY_BIN_COLORS: Record<ActivityRollupBin, string> = {
  active_high: "#10b981", // emerald
  active_mid: "#fb923c", // orange
  weak: "#f59e0b", // amber
  inactive: "#dc2626", // red
};

/**
 * Simple string hash for scaffold IDs — stable integer across calls.
 * Used only when no scaffoldColorForBucket helper exists.
 */
function scaffoldIdHash(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (Math.imul(31, h) + id.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/**
 * Returns the display color for a single UMAP/cluster point given the current
 * color option and per-point paint inputs.
 *
 * Modes:
 *   cluster  — cycles through GROUP_PALETTE by clusterId (modular)
 *   activity — transparent when no curve data; activity-bin color when pIC50 present
 *   scaffold — GROUP_PALETTE keyed by scaffoldId hash; MUTED_GREY when no scaffold
 *   none     — MUTED_GREY (uniform / no coloring)
 */
export function colorForPoint(opt: ColorOption, paint: PointPaint): string {
  switch (opt.mode) {
    case "cluster":
      return GROUP_PALETTE[paint.clusterId % GROUP_PALETTE.length];

    case "activity": {
      if (paint.activityPic50 == null) return "transparent";
      const bin = classifyActivity(paint.activityPic50);
      return bin ? ACTIVITY_BIN_COLORS[bin] : MUTED_GREY;
    }

    case "scaffold":
      if (!paint.scaffoldId) return MUTED_GREY;
      return GROUP_PALETTE[scaffoldIdHash(paint.scaffoldId) % GROUP_PALETTE.length];

    case "none":
      return MUTED_GREY;
  }
}
