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

import { useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";

import { ResultsGridV2 } from "../grid/results-grid";
import { SourceProtocolsList } from "./source-protocols-list";
import { PublishedCollectionLink } from "./published-collection-link";
import { SupersedeDialog } from "./supersede-dialog";

import { HeaderStrip } from "../sections/header-strip";
import { SourcesSection } from "../sections/sources-section";
import { ChannelsSection } from "../sections/channels-section";
import { CampaignToolbar } from "../sections/campaign-toolbar";
import { CampaignReportSheet } from "../sections/campaign-report-sheet";
import {
  CampaignFilterBar,
  emptyFilters,
  type CampaignFilters,
} from "../campaign-filter-bar";

import { useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet } from "@/shared/lib/api/campaigns/campaigns";

import type { CampaignResponse } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface CampaignViewProps {
  campaign: CampaignResponse;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CampaignView({ campaign }: CampaignViewProps) {
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [filters, setFilters] = useState<CampaignFilters>(() => emptyFilters());
  const [reportOpen, setReportOpen] = useState(false);

  // Published endpoint — fetched lazily on download click.
  const { refetch: fetchPublished, isFetching: isDownloading } =
    useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet(
      campaign.id,
      undefined,
      { query: { enabled: false } },
    );

  const handleDownload = async () => {
    const result = await fetchPublished();
    if (!result.data) return;
    const blob = new Blob([JSON.stringify(result.data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `campaign-${campaign.id}-published.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const supersededBy = campaign.superseded_by_campaign_id as
    | string
    | undefined
    | null;
  const supersedesId = campaign.supersedes_campaign_id as
    | string
    | undefined
    | null;
  const closedAt = campaign.closed_at as string | undefined | null;
  const closedBy = campaign.closed_by as string | undefined | null;
  const signatureId = campaign.signature_id as string | undefined | null;

  const sourceProtocols =
    (campaign.source_protocols as Array<Record<string, unknown>>) ?? [];
  const publishedCollectionId = campaign.published_collection_id as
    | string
    | undefined
    | null;

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
        onSupersede={
          campaign.status !== "superseded"
            ? () => setSupersedeOpen(true)
            : undefined
        }
      />
      <SourcesSection
        campaign={campaign}
        projectId={campaign.project_id}
        readOnly
      />
      <ChannelsSection
        campaign={campaign}
        projectId={campaign.project_id}
        readOnly
      />

      {/* Closed-campaign-only details row */}
      <section className="grid grid-cols-1 gap-4 border-b px-6 py-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Source protocols
            </CardTitle>
          </CardHeader>
          <CardContent>
            <SourceProtocolsList protocols={sourceProtocols} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Published collection
            </CardTitle>
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
      />
      <CampaignToolbar
        resultCount={campaign.results?.length ?? 0}
        onCustomizeReport={() => setReportOpen(true)}
        onExport={handleDownload}
        exportDisabled={isDownloading}
      />
      <ResultsGridV2 campaign={campaign} filters={filters} readOnly />

      <SupersedeDialog
        open={supersedeOpen}
        onOpenChange={setSupersedeOpen}
        campaign={campaign}
      />
      <CampaignReportSheet
        open={reportOpen}
        onOpenChange={setReportOpen}
        campaignId={campaign.id}
      />
    </div>
  );
}
