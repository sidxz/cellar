"use client";

/**
 * CampaignBuilder — V2 single-column layout
 *
 * Renders the V2 layout (HeaderStrip + SourcesSection + ChannelsSection +
 * CampaignFilterBar + ResultsGridV2) for draft campaigns.
 * Closed/superseded campaigns dispatch to CampaignView.
 *
 * Note: Path B was chosen over DetailShell wrapping because HeaderStrip IS the
 * campaign's page header — inserting DetailShell's back-button + title row above
 * it would double-header the page. Loading/error/not-found states are aligned
 * with the same primitives DetailShell uses (Skeleton, AlertCircle, ArrowLeft).
 */

import { useAuthzHasRole } from "@duar-auth/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useProject } from "@/features/research-organization/hooks/use-projects";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost } from "@/shared/lib/api/campaigns/campaigns";
import { useBreadcrumbTrail } from "@/shared/lib/stores/breadcrumb-store";
import { showSuccess } from "@/shared/lib/toast";
import { campaignKeys, useCampaign } from "../hooks/use-campaigns";
import { clearedVerdictsNote, qcVerdictsCleared } from "../lib/qc-verdicts";
import type { CampaignResponse, StageOutcome } from "../types";
import { CampaignFilterBar, type CampaignFilters, emptyFilters } from "./campaign-filter-bar";
import { CampaignView } from "./campaign-view";
import { CloseCampaignDialog } from "./close-campaign-dialog";
import { ResultsGridV2 } from "./grid/results-grid";
import { PreviewAsPublishedDialog } from "./preview-as-published-dialog";
import { QcBulkMenu } from "./qc-bulk-menu";
import { StageBulkMenu } from "./stage-bulk-menu";

import { ChannelsSection } from "./sections/channels-section";
// ── V2 section imports ────────────────────────────────────────────────────────
import { HeaderStrip } from "./sections/header-strip";
// import { LibrariesSection } from "./sections/libraries-section"; // section hidden
import { SourcesSection } from "./sections/sources-section";
import { StagesSection } from "./sections/stages-section";

// ── Builder ───────────────────────────────────────────────────────────────────

interface CampaignBuilderProps {
  campaignId: string;
  projectId: string;
}

export function CampaignBuilder({ campaignId, projectId }: CampaignBuilderProps) {
  const { data: campaign, isLoading, error } = useCampaign(campaignId);
  const { data: project } = useProject(projectId);
  const backHref = `/projects/${projectId}/campaigns`;

  // Human-readable breadcrumbs — never display UUIDs.
  useBreadcrumbTrail([
    { label: "Projects", href: "/projects" },
    { label: project?.name ?? "", href: `/projects/${projectId}` },
    { label: "Campaigns", href: backHref },
    { label: campaign?.name ?? "" },
  ]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4 text-muted-foreground">
          {error ? "Failed to load campaign." : "Campaign not found."}
        </p>
        <Button variant="ghost" size="sm" className="mt-4" asChild>
          <Link href={backHref}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Campaigns
          </Link>
        </Button>
      </div>
    );
  }

  if (campaign.status !== "draft") {
    return <CampaignView campaign={campaign} />;
  }

  return <CampaignBuilderV2 campaign={campaign} projectId={projectId} />;
}

// ── V2 shell ──────────────────────────────────────────────────────────────────

function CampaignBuilderV2({
  campaign,
  projectId,
}: {
  campaign: CampaignResponse;
  projectId: string;
}) {
  const qc = useQueryClient();
  const canEditTags = useAuthzHasRole("editor");

  const [filters, setFilters] = useState<CampaignFilters>(() => emptyFilters());
  const [previewOpen, setPreviewOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  // The selection can point at a stage that was just deleted (its popover's
  // own delete flow only closes itself, it doesn't know about this state) —
  // derive back to "All" the moment the campaign refetch confirms it's gone.
  const effectiveStageId = campaign.stages.some((s) => s.id === selectedStageId)
    ? selectedStageId
    : null;

  // Picking a stage tab lenses the grid onto that stage's population
  // (hit + miss + untested + pending) and hides the rows gated out of it; "All"
  // clears the outcome chips again.
  function selectStage(id: string | null) {
    setSelectedStageId(id);
    setFilters((f) => ({
      ...f,
      stageOutcomes: new Set<StageOutcome>(id ? ["hit", "miss", "untested", "pending"] : []),
    }));
  }

  const refreshMutation = useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost({
    mutation: {
      onSuccess: (data) => {
        const before = qc.getQueryData<CampaignResponse>(campaignKeys.detail(campaign.id));
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        const cleared = qcVerdictsCleared(before, data as CampaignResponse);
        if (cleared > 0) showSuccess(`Refreshed${clearedVerdictsNote(cleared)}`);
      },
    },
  });
  const refreshing = refreshMutation.isPending;
  const onRefresh = () => refreshMutation.mutate({ campaignId: campaign.id });

  // Curation (notes, outcome overrides, a cell pick) follows the draft status; structure
  // (sources, columns, stages, compound rows) is also locked when another app manages it.
  const curationLocked = campaign.status !== "draft";
  const structureLocked = curationLocked || Boolean(campaign.managed_by);

  return (
    <div className="flex flex-col">
      <HeaderStrip
        campaign={campaign}
        canEditTags={canEditTags}
        isDraft={campaign.status === "draft"}
        refreshing={refreshing}
        onRefresh={onRefresh}
        onPreview={() => setPreviewOpen(true)}
        onClose={() => setCloseOpen(true)}
      />
      <SourcesSection
        campaign={campaign}
        projectId={projectId}
        readOnly={structureLocked}
        selectedStageId={effectiveStageId}
      />
      {/* Libraries section hidden for now (owner's call, 2026-09-14). The
          backend endpoints and libraries-section.tsx stay as they are —
          uncomment this line and its import to bring the section back. */}
      {/* <LibrariesSection campaign={campaign} readOnly={campaign.status !== "draft"} /> */}
      <ChannelsSection campaign={campaign} projectId={projectId} readOnly={structureLocked} />
      <StagesSection
        campaign={campaign}
        selectedStageId={effectiveStageId}
        onSelectStage={selectStage}
        readOnly={structureLocked}
      />
      <CampaignFilterBar
        campaign={campaign}
        filters={filters}
        onChange={setFilters}
        selectedStageId={effectiveStageId}
        resultCount={campaign.results?.length ?? 0}
      />
      <StageBulkMenu
        campaign={campaign}
        filters={filters}
        selectedStageId={effectiveStageId}
        readOnly={curationLocked}
      />
      <QcBulkMenu
        campaign={campaign}
        filters={filters}
        selectedStageId={effectiveStageId}
        readOnly={curationLocked}
      />
      <ResultsGridV2
        campaign={campaign}
        filters={filters}
        selectedStageId={effectiveStageId}
        readOnly={curationLocked}
        rowsLocked={structureLocked}
      />

      <PreviewAsPublishedDialog
        campaignId={campaign.id}
        campaignName={campaign.name}
        open={previewOpen}
        onOpenChange={setPreviewOpen}
      />
      <CloseCampaignDialog campaign={campaign} open={closeOpen} onOpenChange={setCloseOpen} />
    </div>
  );
}
