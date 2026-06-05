"use client";

import { Button } from "@/shared/components/ui/button";
import { Download } from "lucide-react";

import type { CampaignResponse } from "../../types";
import { BulkDecisionMenu } from "../bulk-decision-menu";
import type { CampaignFilters } from "../campaign-filter-bar";

interface CampaignToolbarProps {
  onExport?: () => void;
  exportDisabled?: boolean;
  //: Bulk-decision menu is rendered when these are supplied. Closed campaigns
  //: pass readOnly so the menu hides itself.
  campaign?: CampaignResponse;
  filters?: CampaignFilters;
  readOnly?: boolean;
}

export function CampaignToolbar({
  onExport,
  exportDisabled,
  campaign,
  filters,
  readOnly,
}: CampaignToolbarProps) {
  const hasBulkMenu = !!(campaign && filters && !readOnly);
  if (!hasBulkMenu && !onExport) {
    // Nothing to show. The result count moved to the filter bar.
    return null;
  }
  return (
    <div className="flex items-center justify-end border-b px-6 py-2 gap-3">
      {campaign && filters && (
        <BulkDecisionMenu campaign={campaign} filters={filters} readOnly={readOnly ?? false} />
      )}
      {onExport && (
        <Button variant="outline" size="sm" onClick={onExport} disabled={exportDisabled}>
          <Download className="h-4 w-4" />
          Export
        </Button>
      )}
    </div>
  );
}
