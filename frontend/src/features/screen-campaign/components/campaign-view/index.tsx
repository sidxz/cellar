"use client";

/**
 * CampaignView — V2 single-column layout, read-only.
 *
 * Reuses the same V2 sections as the draft builder (HeaderStrip,
 * SourcesSection, ChannelsSection, CampaignFilterBar, CampaignToolbar,
 * ResultsGridV2) with `readOnly={true}`. The closed-only details
 * (source protocols, published collection) are surfaced as a small
 * cards row below the channels section. The supersede dialog is
 * preserved and triggered from the HeaderStrip Supersede action.
 */

import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";

import { ResultsGridV2 } from "../grid/results-grid";
import { PublishedCollectionLink } from "./published-collection-link";
import { SourceProtocolsList } from "./source-protocols-list";
import { SupersedeDialog } from "./supersede-dialog";

import {
  CampaignFilterBar,
  type CampaignFilters,
  closedCampaignFilters,
} from "../campaign-filter-bar";
import { ChannelsSection } from "../sections/channels-section";
import { HeaderStrip } from "../sections/header-strip";
import { SourcesSection } from "../sections/sources-section";

import { useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet } from "@/shared/lib/api/campaigns/campaigns";
import { saveText } from "@/shared/lib/api/download";

import type { CampaignResponse } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface CampaignViewProps {
  campaign: CampaignResponse;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CampaignView({ campaign }: CampaignViewProps) {
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const canEditTags = useAuthzHasRole("editor");
  const [filters, setFilters] = useState<CampaignFilters>(() => closedCampaignFilters());

  // Published endpoint — fetched lazily on download click.
  const { refetch: fetchPublished, isFetching: isDownloading } =
    useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet(campaign.id, undefined, {
      query: { enabled: false },
    });

  const handleDownload = async () => {
    const result = await fetchPublished();
    if (!result.data) return;
    saveText(
      JSON.stringify(result.data, null, 2),
      `campaign-${campaign.id}-published.json`,
      "application/json",
    );
  };

  const supersededBy = campaign.superseded_by_campaign_id as string | undefined | null;
  const supersedesId = campaign.supersedes_campaign_id as string | undefined | null;
  const closedAt = campaign.closed_at as string | undefined | null;
  const closedBy = campaign.closed_by as string | undefined | null;
  const signatureId = campaign.signature_id as string | undefined | null;

  const sourceProtocols = (campaign.source_protocols as Array<Record<string, unknown>>) ?? [];
  const publishedCollectionId = campaign.published_collection_id as string | undefined | null;

  return (
    <div className="flex flex-col">
      <HeaderStrip
        campaign={campaign}
        isDraft={false}
        refreshing={false}
        onRefresh={() => {}}
        onPreview={() => {}}
        onCloseAndSign={() => {}}
        closedAt={closedAt}
        closedBy={closedBy}
        signatureId={signatureId}
        supersedesId={supersedesId}
        supersededBy={supersededBy}
        projectId={campaign.project_id}
        onDownload={handleDownload}
        downloadDisabled={isDownloading}
        downloadLabel={isDownloading ? "Downloading…" : undefined}
        onSupersede={campaign.status !== "superseded" ? () => setSupersedeOpen(true) : undefined}
        canEditTags={canEditTags}
      />
      <SourcesSection campaign={campaign} projectId={campaign.project_id} readOnly />
      <ChannelsSection campaign={campaign} projectId={campaign.project_id} readOnly />

      {/* Closed-campaign-only details row */}
      <section className="grid grid-cols-1 gap-4 border-b px-6 py-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Source protocols</CardTitle>
          </CardHeader>
          <CardContent>
            <SourceProtocolsList protocols={sourceProtocols} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Published collection</CardTitle>
          </CardHeader>
          <CardContent>
            <PublishedCollectionLink id={publishedCollectionId} />
          </CardContent>
        </Card>
      </section>

      <CampaignFilterBar
        campaign={campaign}
        filters={filters}
        onChange={setFilters}
        resultCount={campaign.results?.length ?? 0}
      />
      <ResultsGridV2 campaign={campaign} filters={filters} readOnly />

      <SupersedeDialog open={supersedeOpen} onOpenChange={setSupersedeOpen} campaign={campaign} />
    </div>
  );
}
