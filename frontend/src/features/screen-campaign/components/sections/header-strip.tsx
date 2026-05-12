"use client";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { RefreshCw, FileText, Lock } from "lucide-react";
import type { CampaignResponse } from "../../types";
import { CampaignStatusChip } from "../campaign-status-chip";

interface HeaderStripProps {
  campaign: CampaignResponse;
  onRefresh: () => void;
  onPreview: () => void;
  onCloseAndSign: () => void;
  refreshing?: boolean;
  isDraft: boolean;
}

export function HeaderStrip({
  campaign,
  onRefresh,
  onPreview,
  onCloseAndSign,
  refreshing,
  isDraft,
}: HeaderStripProps) {
  const channelCount = campaign.channels?.length ?? 0;
  const compoundCount = campaign.results?.length ?? 0;
  return (
    <header className="flex flex-col gap-1 border-b px-6 py-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{campaign.name}</h1>
        <CampaignStatusChip status={campaign.status} />
        <Badge variant="outline" className="text-xs">
          {channelCount} {channelCount === 1 ? "channel" : "channels"}
        </Badge>
        <Badge variant="outline" className="text-xs">
          {compoundCount} {compoundCount === 1 ? "compound" : "compounds"}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          {isDraft && (
            <>
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={onPreview}>
                <FileText className="h-4 w-4" />
                Preview as published
              </Button>
              <Button size="sm" onClick={onCloseAndSign}>
                <Lock className="h-4 w-4" />
                Close &amp; Sign
              </Button>
            </>
          )}
        </div>
      </div>
      {campaign.description && (
        <p className="text-sm text-muted-foreground">{campaign.description}</p>
      )}
    </header>
  );
}
