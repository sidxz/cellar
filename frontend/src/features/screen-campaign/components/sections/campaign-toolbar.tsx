"use client";

import { Button } from "@/shared/components/ui/button";
import { Download, Settings2 } from "lucide-react";

interface CampaignToolbarProps {
  resultCount: number;
  onCustomizeReport: () => void;
  onExport?: () => void;
  exportDisabled?: boolean;
}

export function CampaignToolbar({
  resultCount,
  onCustomizeReport,
  onExport,
  exportDisabled,
}: CampaignToolbarProps) {
  return (
    <div className="flex items-center justify-between border-b px-6 py-2">
      <span className="text-sm text-muted-foreground">{resultCount} results</span>
      <div className="flex items-center gap-2">
        {onExport && (
          <Button variant="outline" size="sm" onClick={onExport} disabled={exportDisabled}>
            <Download className="h-4 w-4" />
            Export
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onCustomizeReport}>
          <Settings2 className="h-4 w-4" />
          Customize Report
        </Button>
      </div>
    </div>
  );
}
