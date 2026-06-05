"use client";

/**
 * CampaignBuilder — V2 single-column layout
 *
 * Renders the V2 layout (HeaderStrip + SourcesSection + ChannelsSection +
 * CampaignFilterBar + CampaignToolbar + ResultsGridV2) for draft campaigns.
 * Closed/superseded campaigns dispatch to CampaignView.
 *
 * Note: Path B was chosen over DetailShell wrapping because HeaderStrip IS the
 * campaign's page header — inserting DetailShell's back-button + title row above
 * it would double-header the page. Loading/error/not-found states are aligned
 * with the same primitives DetailShell uses (Skeleton, AlertCircle, ArrowLeft).
 */

import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useProject } from "@/features/research-organization/hooks/use-projects";
import { useBreadcrumbTrail } from "@/shared/components/layout/breadcrumb-context";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys, useCampaign } from "../hooks/use-campaigns";
import type { CampaignResponse } from "../types";
import { CampaignFilterBar, type CampaignFilters, emptyFilters } from "./campaign-filter-bar";
import { CampaignView } from "./campaign-view";
import { CloseSignDialog } from "./close-sign-dialog";
import { ResultsGridV2 } from "./grid/results-grid";
import { PreviewAsPublishedDialog } from "./preview-as-published-dialog";

import { CampaignToolbar } from "./sections/campaign-toolbar";
import { ChannelsSection } from "./sections/channels-section";
// ── V2 section imports ────────────────────────────────────────────────────────
import { HeaderStrip } from "./sections/header-strip";
import { SourcesSection } from "./sections/sources-section";

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
        canEditTags={canEditTags}
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
      <ResultsGridV2 campaign={campaign} filters={filters} readOnly={campaign.status !== "draft"} />

      <PreviewAsPublishedDialog
        campaignId={campaign.id}
        campaignName={campaign.name}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      />
      <CloseSignDialog campaign={campaign} open={closeSignOpen} onOpenChange={setCloseSignOpen} />
    </div>
  );
}
