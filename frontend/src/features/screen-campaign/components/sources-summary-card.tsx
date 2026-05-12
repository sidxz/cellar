"use client";

/**
 * SourcesSummaryCard
 *
 * Displays where each compound in the campaign came from. Reads
 * `campaign.compound_sources` (derived server-side from per-result
 * added_from attribution). Name lookups for Collection / Campaign / Run
 * refs are done concurrently via TanStack Query. Never displays raw UUIDs.
 *
 * Renders nothing when the campaign has no results.
 */

import {
  useGetCampaignApiV1CampaignsCampaignIdGet,
} from "@/shared/lib/api/campaigns/campaigns";
import { useGetCollectionApiV1CollectionsCollectionIdGet } from "@/shared/lib/api/collections/collections";
import { useGetRunApiV1RunsRunIdGet } from "@/shared/lib/api/runs/runs";
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
  const { data: collection } = useGetCollectionApiV1CollectionsCollectionIdGet(
    collectionId,
    { query: { staleTime: 60_000 } },
  );
  // Order of preference: caller-supplied description > collection name > generic.
  const label = description ?? collection?.name ?? "Collection";
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
  const name = description ?? campaign?.name ?? "Campaign";
  return <>{name}</>;
}

function RunLabel({
  runId,
  description,
}: {
  runId: string;
  description?: string | null;
}) {
  const { data: run } = useGetRunApiV1RunsRunIdGet(runId, {
    query: { staleTime: 60_000 },
  });
  if (description) return <>{description}</>;
  if (!run) return <>Run</>;
  // No human-friendly run name in the schema; show the run date — that's how
  // chemists actually identify a run ("the one from May 7th").
  const date = run.run_date
    ? new Date(run.run_date as unknown as string).toLocaleDateString()
    : null;
  return <>{date ? `Run on ${date}` : "Run"}</>;
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
              {s.kind === "run" && s.run_id && (
                <RunLabel runId={s.run_id} description={s.description} />
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
