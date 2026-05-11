import { Badge } from "@/shared/components/ui/badge";
import type { CampaignStatus } from "../types";

interface CampaignStatusChipProps {
  /** The campaign's status string from the API response. */
  status: string;
}

/**
 * A small, color-coded Badge that surfaces a campaign's lifecycle status.
 * Accepts the raw `status` string from the API so the component stays
 * usable even when the status value is unexpected (renders an outline badge).
 */
export function CampaignStatusChip({ status }: CampaignStatusChipProps) {
  const s = status as CampaignStatus;
  switch (s) {
    case "draft":
      return <Badge variant="secondary">Draft</Badge>;
    case "closed":
      return <Badge variant="default">Closed</Badge>;
    case "superseded":
      return <Badge variant="outline">Superseded</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}
