"use client";

/**
 * AddCompoundsPills — Task 2.3
 *
 * Renders four + Add pills (Run / Collection / Campaign / Manual) and owns
 * their dialog open-state. Wraps the four existing add-compound dialogs
 * without changing their internal behavior.
 */

import { Plus } from "lucide-react";
import { useState } from "react";

import type { CampaignResponse } from "../../types";
import { AddFromCampaignDialog } from "../add-from-campaign-dialog";
import { AddFromCollectionDialog } from "../add-from-collection-dialog";
import { AddFromRunsDialog } from "../add-from-runs-dialog";
import { ManualAddDialog } from "./manual-add-dialog";

interface AddCompoundsPillsProps {
  campaign: CampaignResponse;
  projectId: string;
  disabled?: boolean;
}

const PILL_CLASS =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50 transition-colors";

export function AddCompoundsPills({ campaign, projectId, disabled }: AddCompoundsPillsProps) {
  const [open, setOpen] = useState<"run" | "collection" | "campaign" | "manual" | null>(null);

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          className={PILL_CLASS}
          disabled={disabled}
          onClick={() => setOpen("run")}
        >
          <Plus className="h-3 w-3" />
          Run
        </button>
        <button
          type="button"
          className={PILL_CLASS}
          disabled={disabled}
          onClick={() => setOpen("collection")}
        >
          <Plus className="h-3 w-3" />
          Collection
        </button>
        <button
          type="button"
          className={PILL_CLASS}
          disabled={disabled}
          onClick={() => setOpen("campaign")}
        >
          <Plus className="h-3 w-3" />
          Campaign
        </button>
        <button
          type="button"
          className={PILL_CLASS}
          disabled={disabled}
          onClick={() => setOpen("manual")}
        >
          <Plus className="h-3 w-3" />
          Manual
        </button>
      </div>

      <AddFromRunsDialog
        campaignId={campaign.id}
        projectId={projectId}
        open={open === "run"}
        onOpenChange={(v) => !v && setOpen(null)}
      />
      <AddFromCollectionDialog
        campaignId={campaign.id}
        projectId={projectId}
        open={open === "collection"}
        onOpenChange={(v) => !v && setOpen(null)}
      />
      <AddFromCampaignDialog
        campaignId={campaign.id}
        projectId={projectId}
        open={open === "campaign"}
        onOpenChange={(v) => !v && setOpen(null)}
      />
      <ManualAddDialog
        campaignId={campaign.id}
        open={open === "manual"}
        onOpenChange={(v) => !v && setOpen(null)}
      />
    </>
  );
}
