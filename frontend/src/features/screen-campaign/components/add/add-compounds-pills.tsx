"use client";

/**
 * AddCompoundsPills — Task 2.3
 *
 * Renders four + Add pills (Run / Collection / Campaign / Manual) and the
 * four add-compound dialogs they open. Dialog open-state is controlled by
 * the parent (via `open` / `onOpenChange`) so sibling affordances — e.g.
 * the Source Compounds empty-state "Import from Runs" link — can open the
 * same dialogs. Dialog internals are unchanged.
 */

import { Plus } from "lucide-react";

import type { CampaignResponse } from "../../types";
import { AddFromCampaignDialog } from "../add-from-campaign-dialog";
import { AddFromCollectionDialog } from "../add-from-collection-dialog";
import { AddFromRunsDialog } from "../add-from-runs-dialog";
import { ManualAddDialog } from "./manual-add-dialog";

export type AddCompoundsKind = "run" | "collection" | "campaign" | "manual";

interface AddCompoundsPillsProps {
  campaign: CampaignResponse;
  projectId: string;
  disabled?: boolean;
  /** Controlled open-state — lets sibling affordances (e.g. the empty-state
   *  "Import from Runs" link) trigger the same dialogs. */
  open: AddCompoundsKind | null;
  onOpenChange: (kind: AddCompoundsKind | null) => void;
}

const PILL_CLASS =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50 transition-colors";

export function AddCompoundsPills({
  campaign,
  projectId,
  disabled,
  open,
  onOpenChange,
}: AddCompoundsPillsProps) {
  const setOpen = onOpenChange;

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
