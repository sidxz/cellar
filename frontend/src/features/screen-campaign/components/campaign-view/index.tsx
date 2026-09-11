"use client";

/**
 * CampaignView — V2 single-column layout, read-only.
 *
 * Reuses the same V2 sections as the draft builder (HeaderStrip,
 * SourcesSection, ChannelsSection, CampaignFilterBar, ResultsGridV2) with `readOnly={true}`. The closed-only detail
 * (source protocols) is surfaced as a small card below the channels
 * section. The supersede dialog is preserved and triggered from the
 * HeaderStrip Supersede action.
 */

import { useAuthzHasRole } from "@duar-auth/nextjs";
import { useState } from "react";

import { TagTable } from "@/features/tagging/components/tag-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";

import { ResultsGridV2 } from "../grid/results-grid";
import { ReopenDialog } from "./reopen-dialog";
import { SourceProtocolsList } from "./source-protocols-list";
import { SupersedeDialog } from "./supersede-dialog";

import { CampaignFilterBar, type CampaignFilters, emptyFilters } from "../campaign-filter-bar";
import { ChannelsSection } from "../sections/channels-section";
import { HeaderStrip } from "../sections/header-strip";
import { SourcesSection } from "../sections/sources-section";
import { StagesSection } from "../sections/stages-section";

import { useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet } from "@/shared/lib/api/campaigns/campaigns";
import { saveText } from "@/shared/lib/api/download";

import type { CampaignResponse, StageOutcome } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface CampaignViewProps {
  campaign: CampaignResponse;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CampaignView({ campaign }: CampaignViewProps) {
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const canEditTags = useAuthzHasRole("editor");
  const [filters, setFilters] = useState<CampaignFilters>(() => emptyFilters());
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  // Closed campaigns are read-only, but a superseding refresh can still
  // drop a stage out from under the current selection — derive back to
  // "All" the moment that happens rather than pointing at a stale id.
  const effectiveStageId = campaign.stages.some((s) => s.id === selectedStageId)
    ? selectedStageId
    : null;

  // Same lens as the draft builder: a stage tab pre-selects its population
  // (hit + miss + untested); "All" clears the outcome chips.
  function selectStage(id: string | null) {
    setSelectedStageId(id);
    setFilters((f) => ({
      ...f,
      stageOutcomes: new Set<StageOutcome>(id ? ["hit", "miss", "untested"] : []),
    }));
  }

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

  const sourceProtocols = (campaign.source_protocols as Array<Record<string, unknown>>) ?? [];

  return (
    <div className="flex flex-col">
      <HeaderStrip
        campaign={campaign}
        isDraft={false}
        refreshing={false}
        onRefresh={() => {}}
        onPreview={() => {}}
        onClose={() => {}}
        closedAt={closedAt}
        closedBy={closedBy}
        supersedesId={supersedesId}
        supersededBy={supersededBy}
        projectId={campaign.project_id}
        onDownload={handleDownload}
        downloadDisabled={isDownloading}
        downloadLabel={isDownloading ? "Downloading…" : undefined}
        onSupersede={campaign.status !== "superseded" ? () => setSupersedeOpen(true) : undefined}
        onReopen={() => setReopenOpen(true)}
      />
      <SourcesSection campaign={campaign} projectId={campaign.project_id} readOnly />
      <ChannelsSection campaign={campaign} projectId={campaign.project_id} readOnly />
      <StagesSection
        campaign={campaign}
        selectedStageId={effectiveStageId}
        onSelectStage={selectStage}
        readOnly
      />

      {/* Closed-campaign-only detail */}
      <section className="border-b px-6 py-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Source protocols</CardTitle>
          </CardHeader>
          <CardContent>
            <SourceProtocolsList protocols={sourceProtocols} />
          </CardContent>
        </Card>
      </section>

      <CampaignFilterBar
        campaign={campaign}
        filters={filters}
        onChange={setFilters}
        selectedStageId={effectiveStageId}
        resultCount={campaign.results?.length ?? 0}
      />
      <ResultsGridV2
        campaign={campaign}
        filters={filters}
        selectedStageId={effectiveStageId}
        readOnly
      />

      <section className="border-t px-6 py-4">
        <TagTable entity="campaigns" entityId={campaign.id} canEdit={canEditTags} />
      </section>

      <SupersedeDialog open={supersedeOpen} onOpenChange={setSupersedeOpen} campaign={campaign} />
      <ReopenDialog campaign={campaign} open={reopenOpen} onOpenChange={setReopenOpen} />
    </div>
  );
}
