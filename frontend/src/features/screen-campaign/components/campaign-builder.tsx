"use client";

/**
 * CampaignBuilder — V2 single-column layout
 *
 * Renders the V2 layout (HeaderStrip + SourcesSection + ChannelsSection +
 * CampaignFilterBar + CampaignToolbar + ResultsGridV2) for draft campaigns.
 * Closed/superseded campaigns dispatch to CampaignView.
 */

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useCampaign, campaignKeys } from "../lib/hooks";
import { useProject } from "@/features/research-organization/hooks/use-projects";
import { useBreadcrumbTrail } from "@/shared/components/layout/breadcrumb-context";
import { ResultsGridV2 } from "./grid/results-grid";
import { CloseSignDialog } from "./close-sign-dialog";
import { CampaignView } from "./campaign-view";
import {
  CampaignFilterBar,
  emptyFilters,
  type CampaignFilters,
} from "./campaign-filter-bar";
import { PreviewAsPublishedDialog } from "./preview-as-published-dialog";
import { useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost } from "@/shared/lib/api/campaigns/campaigns";
import type { CampaignResponse } from "../types";

// ── V2 section imports ────────────────────────────────────────────────────────
import { HeaderStrip } from "./sections/header-strip";
import { SourcesSection } from "./sections/sources-section";
import { ChannelsSection } from "./sections/channels-section";
import { CampaignToolbar } from "./sections/campaign-toolbar";

// ── Builder ───────────────────────────────────────────────────────────────────

interface CampaignBuilderProps {
  campaignId: string;
  projectId: string;
}

export function CampaignBuilder({ campaignId, projectId }: CampaignBuilderProps) {
  const { data: campaign, isLoading, error } = useCampaign(campaignId);
  const { data: project } = useProject(projectId);

  // Human-readable breadcrumbs — never display UUIDs.
  useBreadcrumbTrail([
    { label: "Projects", href: "/projects" },
    { label: project?.name ?? "", href: `/projects/${projectId}` },
    { label: "Campaigns", href: `/projects/${projectId}/campaigns` },
    { label: campaign?.name ?? "" },
  ]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <p className="text-destructive p-6">
        Failed to load campaign. Please refresh the page.
      </p>
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

  const [filters, setFilters] = useState<CampaignFilters>(() => emptyFilters());
  const [previewOpen, setPreviewOpen] = useState(false);
  const [closeSignOpen, setCloseSignOpen] = useState(false);

  const refreshMutation = useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
      },
    },
  });
  const refreshing = refreshMutation.isPending;
  const onRefresh = () => refreshMutation.mutate({ campaignId: campaign.id });

  return (
    <div className="flex flex-col">
      <HeaderStrip
        campaign={campaign}
        isDraft={campaign.status === "draft"}
        refreshing={refreshing}
        onRefresh={onRefresh}
        onPreview={() => setPreviewOpen(true)}
        onCloseAndSign={() => setCloseSignOpen(true)}
      />
      <SourcesSection
        campaign={campaign}
        projectId={projectId}
        readOnly={campaign.status !== "draft"}
      />
      <ChannelsSection
        campaign={campaign}
        projectId={projectId}
        readOnly={campaign.status !== "draft"}
      />
      <CampaignFilterBar
        campaign={campaign}
        filters={filters}
        onChange={setFilters}
        resultCount={campaign.results?.length ?? 0}
      />
      <CampaignToolbar
        campaign={campaign}
        filters={filters}
        readOnly={campaign.status !== "draft"}
      />
      <ResultsGridV2
        campaign={campaign}
        filters={filters}
        readOnly={campaign.status !== "draft"}
      />

      <PreviewAsPublishedDialog
        campaignId={campaign.id}
        campaignName={campaign.name}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      />
      <CloseSignDialog
        campaign={campaign}
        open={closeSignOpen}
        onOpenChange={setCloseSignOpen}
      />
    </div>
  );
}
