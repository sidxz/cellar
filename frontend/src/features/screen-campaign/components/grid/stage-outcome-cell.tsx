"use client";

/**
 * StageOutcomeCell — the grid's "Stage" column, rendered only while a hit
 * stage is selected. Shows this result's outcome for that stage plus an OVR
 * marker when the outcome was forced; in draft the chip opens
 * <StageOverridePopover> so the chemist can promote/demote from the grid.
 */

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/shared/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";

import { outcomeFor } from "../../lib/stage-outcomes";
import type { CampaignResultResponse, CampaignStageResponse, StageOutcome } from "../../types";
import { StageOverridePopover } from "../popovers/stage-override-popover";

const CHIP_CLASS: Record<StageOutcome, string> = {
  hit: "border-success/40 bg-success/10 text-success",
  miss: "border-muted text-muted-foreground",
  untested: "border-warning/40 bg-warning/10 text-warning",
  pending: "border-blue-300 bg-blue-50 text-blue-800 dark:bg-blue-950/40 dark:text-blue-200",
  not_in_stage: "border-transparent bg-muted/60 text-muted-foreground/70",
};

const CHIP_LABEL: Record<StageOutcome, string> = {
  hit: "hit",
  miss: "miss",
  untested: "untested",
  pending: "pending",
  not_in_stage: "not in stage",
};

interface StageOutcomeCellProps {
  campaignId: string;
  result: CampaignResultResponse;
  stage: CampaignStageResponse;
  channelLabelById: ReadonlyMap<string, string>;
  readOnly: boolean;
}

export function StageOutcomeCell({
  campaignId,
  result,
  stage,
  channelLabelById,
  readOnly,
}: StageOutcomeCellProps) {
  const [open, setOpen] = useState(false);

  const outcome = outcomeFor(result, stage.id);
  const value = (outcome?.outcome ?? "not_in_stage") as StageOutcome;

  const chip = (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${CHIP_CLASS[value]}`}
    >
      {CHIP_LABEL[value]}
      {outcome?.overridden && (
        <Badge
          variant="outline"
          className="text-[10px]"
          title={outcome.override_reason ?? "Manually overridden"}
        >
          OVR
        </Badge>
      )}
      {!readOnly && <ChevronDown className="h-3 w-3" />}
    </span>
  );

  if (readOnly) {
    return <div className="flex items-start py-1">{chip}</div>;
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="flex items-start py-1 text-left">
          {chip}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <StageOverridePopover
          campaignId={campaignId}
          result={result}
          stage={stage}
          outcome={outcome}
          channelLabelById={channelLabelById}
          onClose={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}
