"use client";

/**
 * SourcesSummaryCard
 *
 * Displays where each compound in the campaign came from. Reads
 * `campaign.compound_sources` (derived server-side from per-result
 * added_from attribution). Name lookups for Collection / Campaign / Run
 * refs are done concurrently via TanStack Query.
 *
 * Renders nothing when the campaign has no results.
 */

import {
  useGetCampaignApiV1CampaignsCampaignIdGet,
} from "@/shared/lib/api/campaigns/campaigns";
import type { CampaignResponse } from "../types";

// ── Type helpers ─────────────────────────────────────────────────────────────

type SourceEntry = {
  kind: string;
  collection_id?: string;
  campaign_id?: string;
  run_id?: string;
  description?: string | null;
  count: number;
};

// ── Sub-components for name resolution ───────────────────────────────────────

function CollectionLabel({
  collectionId,
  description,
}: {
  collectionId: string;
  description?: string | null;
}) {
  // Use the collection name from the general list if loaded, or fall back to ID prefix
  const label = description ?? `Collection …${collectionId.slice(-6)}`;
  return <>{label}</>;
}

function CampaignLabel({
  campaignId,
  description,
}: {
  campaignId: string;
  description?: string | null;
}) {
  const { data: campaign } = useGetCampaignApiV1CampaignsCampaignIdGet(campaignId, {
    query: { staleTime: 60_000 },
  });
  const name = campaign?.name ?? description ?? `Campaign …${campaignId.slice(-6)}`;
  return <>{name}</>;
}

// ── Main component ────────────────────────────────────────────────────────────

interface SourcesSummaryCardProps {
  campaign: CampaignResponse;
}

export function SourcesSummaryCard({ campaign }: SourcesSummaryCardProps) {
  const sources = campaign.compound_sources as SourceEntry[];

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs min-w-[160px]">
      <p className="font-medium text-muted-foreground mb-1.5 uppercase tracking-wide text-[10px]">
        Sources
      </p>
      <ul className="space-y-1">
        {sources.map((s, i) => (
          <li key={i} className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground truncate max-w-[180px]">
              {s.kind === "manual" && "Manual"}
              {s.kind === "collection" && s.collection_id && (
                <CollectionLabel
                  collectionId={s.collection_id}
                  description={s.description}
                />
              )}
              {s.kind === "campaign" && s.campaign_id && (
                <CampaignLabel
                  campaignId={s.campaign_id}
                  description={s.description}
                />
              )}
              {s.kind === "run" && (
                <>Run …{s.run_id?.slice(-6) ?? "?"}</>
              )}
              {!["manual", "collection", "campaign", "run"].includes(s.kind) && s.kind}
            </span>
            <span className="font-mono tabular-nums text-foreground shrink-0">
              {s.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
