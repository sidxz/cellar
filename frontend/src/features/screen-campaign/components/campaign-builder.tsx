"use client";

/**
 * CampaignBuilder — Task 8.2 (builder shell)
 *
 * 3-pane grid layout:
 *   left  (300 px) — compound list
 *   center         — channel strip + results grid
 *   right (300 px) — decision panel (shown when a row is selected)
 *
 * If the campaign status !== "draft", renders the CampaignView placeholder.
 */

import { useState } from "react";
import { FileJson, Loader2, RefreshCw, Lock } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";

import { useCampaign, campaignKeys } from "../lib/hooks";
import { CampaignStatusChip } from "./campaign-status-chip";
import { ChannelStrip } from "./channel-strip";
import { ResultsGrid } from "./results-grid";
import { DecisionPanel } from "./decision-panel";
import { CompoundListPane } from "./compound-list-pane";
import { CloseSignDialog } from "./close-sign-dialog";
import { CampaignView } from "./campaign-view";
import { SourcesSummaryCard } from "./sources-summary-card";
import {
  CampaignFilterBar,
  emptyFilters,
  type CampaignFilters,
} from "./campaign-filter-bar";
import { PreviewAsPublishedDialog } from "./preview-as-published-dialog";
import { useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost } from "@/shared/lib/api/campaigns/campaigns";
import type { CampaignResultResponse } from "../types";

// ── Builder ───────────────────────────────────────────────────────────────────

interface CampaignBuilderProps {
  campaignId: string;
  projectId: string;
}

export function CampaignBuilder({ campaignId, projectId }: CampaignBuilderProps) {
  const qc = useQueryClient();
  const { data: campaign, isLoading, error } = useCampaign(campaignId);
  const [selectedResult, setSelectedResult] = useState<CampaignResultResponse | null>(null);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [previewPublishedOpen, setPreviewPublishedOpen] = useState(false);
  const [filters, setFilters] = useState<CampaignFilters>(() => emptyFilters());

  const refreshMutation = useRefreshCampaignApiV1CampaignsCampaignIdRefreshPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
      },
    },
  });

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

  return (
    <div className="flex flex-col h-screen">
      {/* ── Sticky header ── */}
      <header className="sticky top-0 z-20 bg-background border-b px-4 py-3 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-semibold truncate">{campaign.name}</h1>
            <CampaignStatusChip status={campaign.status} />
            {campaign.channels.length > 0 && (
              <Badge variant="secondary">{campaign.channels.length} channels</Badge>
            )}
            {campaign.results.length > 0 && (
              <Badge variant="secondary">{campaign.results.length} compounds</Badge>
            )}
          </div>
          {campaign.description && (
            <p className="text-sm text-muted-foreground truncate mt-0.5">
              {campaign.description as string}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <SourcesSummaryCard campaign={campaign} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => refreshMutation.mutate({ campaignId })}
            disabled={refreshMutation.isPending}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPreviewPublishedOpen(true)}
          >
            <FileJson className="mr-2 h-4 w-4" />
            Preview as published
          </Button>
          <Button
            size="sm"
            onClick={() => setCloseDialogOpen(true)}
          >
            <Lock className="mr-2 h-4 w-4" />
            Close &amp; Sign
          </Button>
        </div>
      </header>

      {/* ── 3-pane grid ── */}
      <div className="grid grid-cols-[300px_1fr_300px] gap-0 flex-1 min-h-0 overflow-hidden">
        {/* Left — compound list */}
        <aside className="border-r overflow-y-auto">
          <CompoundListPane
            campaign={campaign}
            selectedResultId={selectedResult?.id ?? null}
            onSelectResult={setSelectedResult}
          />
        </aside>

        {/* Center — channel strip + filter bar + results grid */}
        <main className="flex flex-col overflow-hidden">
          <ChannelStrip campaign={campaign} />
          <CampaignFilterBar
            campaign={campaign}
            filters={filters}
            onChange={setFilters}
          />
          <div className="flex-1 overflow-auto p-2">
            <ResultsGrid
              campaign={campaign}
              selectedResultId={selectedResult?.id ?? null}
              onRowSelect={setSelectedResult}
              filters={filters}
            />
          </div>
        </main>

        {/* Right — decision panel */}
        <aside className="border-l overflow-y-auto">
          {selectedResult ? (
            <DecisionPanel
              campaignId={campaignId}
              result={selectedResult}
              channel={campaign.channels.find(
                (ch) =>
                  selectedResult.measurements.find((m) => m.channel_id === ch.id)
              ) ?? null}
              onUpdate={() => {
                void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
              }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-center p-6">
              <p className="text-sm text-muted-foreground">
                Select a compound row to review its decision.
              </p>
            </div>
          )}
        </aside>
      </div>

      {/* Close & sign dialog */}
      <CloseSignDialog
        campaign={campaign}
        open={closeDialogOpen}
        onOpenChange={setCloseDialogOpen}
      />

      {/* Preview as published */}
      <PreviewAsPublishedDialog
        campaignId={campaign.id}
        campaignName={campaign.name}
        open={previewPublishedOpen}
        onClose={() => setPreviewPublishedOpen(false)}
      />
    </div>
  );
}
