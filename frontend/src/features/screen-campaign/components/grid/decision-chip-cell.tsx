"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { CampaignResultResponse } from "../../types";
import { DecisionPopover } from "../popovers/decision-popover";

interface DecisionChipCellProps {
  campaignId: string;
  result: CampaignResultResponse;
  readOnly: boolean;
}

const CHIP_CLASS: Record<string, string> = {
  selected: "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300",
  deferred: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  rejected: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
};

export function DecisionChipCell({ campaignId, result, readOnly }: DecisionChipCellProps) {
  const [open, setOpen] = useState(false);
  const dec = (result.decision ?? "deferred") as keyof typeof CHIP_CLASS;
  const reason = (result.decision_reason as string | null | undefined)?.trim();
  const notes = (result.notes as string | null | undefined)?.trim();

  const chip = (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${CHIP_CLASS[dec]}`}
    >
      {dec}
      {!readOnly && <ChevronDown className="h-3 w-3" />}
    </span>
  );

  // Vertical detail strip: shows the captured reason and notes below the chip
  // so the chemist can read past triage rationale without opening the popover.
  // Each line is clamped to 2 lines; full text is available via the title
  // tooltip on hover and inside the popover when editing.
  const detail = (reason || notes) && (
    <div className="mt-1.5 space-y-1 text-[11px] leading-tight max-w-[200px]">
      {reason && (
        <p className="text-muted-foreground line-clamp-2" title={reason}>
          <span className="font-medium text-foreground/70">Reason:</span> {reason}
        </p>
      )}
      {notes && (
        <p className="text-muted-foreground/80 italic line-clamp-2" title={notes}>
          {notes}
        </p>
      )}
    </div>
  );

  if (readOnly) {
    return (
      <div className="flex flex-col items-start py-1">
        {chip}
        {detail}
      </div>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="flex flex-col items-start py-1 text-left">
          {chip}
          {detail}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <DecisionPopover campaignId={campaignId} result={result} onClose={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
