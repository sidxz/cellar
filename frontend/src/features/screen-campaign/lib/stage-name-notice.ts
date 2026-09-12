import type { CampaignStageResponse } from "../types";

/**
 * What to tell the user about a `stage_name` that already exists on the
 * campaign.
 *
 * The backend get-or-creates a stage by name (case-insensitive) and replaces
 * its criteria, so a collision is normal — an advisory, not an error. The one
 * exception is a manual stage: its membership is hand-picked, not rule-driven,
 * so the backend 422s rather than overwrite it.
 */
export function stageNameNotice(
  stages: CampaignStageResponse[],
  name: string,
): { text: string; blocking: boolean } | null {
  const trimmed = name.trim().toLowerCase();
  if (!trimmed) return null;
  const match = stages.find((s) => s.name.toLowerCase() === trimmed);
  if (!match) return null;
  return match.kind === "manual"
    ? { text: `${match.name} is a manual stage; pick another name`, blocking: true }
    : { text: `Reuses stage "${match.name}": its criteria will be replaced.`, blocking: false };
}
