import type { AcceptMeltingStepItem } from "@/shared/lib/api/model";
import type { MeltingAnalysis } from "../types";

/** The unreviewed peaks that give a Tm in a window on `channel`: what "Accept all"
 *  accepts. A position with a peak issue has no such peak in that window, so it is
 *  left out, and so is a peak that lies outside every window. */
export function peaksToAccept(
  analysis: Pick<MeltingAnalysis, "windows" | "steps">,
  channel: string | null,
): AcceptMeltingStepItem[] {
  const named = new Set(
    analysis.windows
      .filter((w) => w.channel_key === channel)
      .flatMap((w) => w.positions.map((p) => p.step_id)),
  );
  return analysis.steps
    .filter((s) => s.status === "unreviewed" && named.has(s.id))
    .map((s) => ({ id: s.id, expected_version: s.version }));
}
