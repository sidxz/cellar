"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
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
  const chip = (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${CHIP_CLASS[dec]}`}>
      {dec}
      {!readOnly && <ChevronDown className="h-3 w-3" />}
    </span>
  );
  if (readOnly) return chip;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button">{chip}</button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <DecisionPopover
          campaignId={campaignId}
          result={result}
          onClose={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}
