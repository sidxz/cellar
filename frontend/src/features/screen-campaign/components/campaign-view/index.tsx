"use client";

/**
 * CampaignView — Task 9.1
 *
 * Read-only view for closed / superseded campaigns.
 * Renders: header card (name, status, supersedes links, signature info),
 * source protocols, published collection link, and read-only ResultsGrid.
 */

import { useState } from "react";
import Link from "next/link";
import { Download, Lock, ArrowRight, AlertTriangle } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Separator } from "@/shared/components/ui/separator";

import { CampaignStatusChip } from "../campaign-status-chip";
import { ResultsGrid } from "../results-grid";
import { SourceProtocolsList } from "./source-protocols-list";
import { PublishedCollectionLink } from "./published-collection-link";
import { SupersedeDialog } from "./supersede-dialog";

import { useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet } from "@/shared/lib/api/campaigns/campaigns";

import type { CampaignResponse } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface CampaignViewProps {
  campaign: CampaignResponse;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CampaignView({ campaign }: CampaignViewProps) {
  const [supersedeOpen, setSupersedeOpen] = useState(false);

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

  const supersededBy = campaign.superseded_by_campaign_id as string | undefined | null;
  const supersedesId = campaign.supersedes_campaign_id as string | undefined | null;
  const closedAt = campaign.closed_at as string | undefined | null;
  const closedBy = campaign.closed_by as string | undefined | null;
  const signatureId = campaign.signature_id as string | undefined | null;

  return (
    <div className="flex flex-col h-screen">
      {/* ── Sticky header ── */}
      <header className="sticky top-0 z-20 bg-background border-b px-4 py-3">
        {/* Superseded-by banner */}
        {supersededBy && (
          <div className="mb-3 flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              This campaign was superseded by{" "}
              <Link
                href={`/projects/${campaign.project_id}/campaigns/${supersededBy}`}
                className="font-medium underline underline-offset-2 hover:opacity-80"
              >
                a newer campaign
              </Link>
              .
            </span>
          </div>
        )}

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg font-semibold truncate">{campaign.name}</h1>
              <CampaignStatusChip status={campaign.status} />

              {supersedesId && (
                <Badge variant="outline" className="text-xs gap-1">
                  <ArrowRight className="h-3 w-3" />
                  Supersedes{" "}
                  <Link
                    href={`/projects/${campaign.project_id}/campaigns/${supersedesId}`}
                    className="underline underline-offset-2 hover:opacity-80"
                  >
                    prior campaign
                  </Link>
                </Badge>
              )}
            </div>

            {/* Closed-at / closed-by / signature */}
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-xs text-muted-foreground">
              {closedAt && (
                <span>
                  Closed{" "}
                  {new Date(closedAt).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
              )}
              {/* closed_by + signature_id are backend UUIDs. Name + signed_at
                  resolution via Sentinel/audit is a known follow-up (A2 in
                  the backlog); until then, show a non-UUID placeholder. */}
              {closedBy && <span>Signed off by author</span>}
              {signatureId && <span>Electronic signature recorded</span>}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={isDownloading}
            >
              <Download className="mr-2 h-4 w-4" />
              {isDownloading ? "Downloading…" : "Download JSON"}
            </Button>

            {campaign.status !== "superseded" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSupersedeOpen(true)}
              >
                <Lock className="mr-2 h-4 w-4" />
                Supersede
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Source protocols + collection row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Source protocols
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SourceProtocolsList
                protocols={
                  campaign.source_protocols as Array<Record<string, unknown>>
                }
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Published collection
              </CardTitle>
            </CardHeader>
            <CardContent>
              <PublishedCollectionLink
                id={campaign.published_collection_id as string | undefined | null}
              />
            </CardContent>
          </Card>
        </div>

        <Separator />

        {/* Read-only results grid */}
        <div className="h-[600px]">
          <ResultsGrid
            campaign={campaign}
            selectedResultId={null}
            onRowSelect={() => {}}
            readOnly
          />
        </div>
      </div>

      {/* Supersede dialog */}
      <SupersedeDialog
        open={supersedeOpen}
        onOpenChange={setSupersedeOpen}
        campaign={campaign}
      />
    </div>
  );
}
