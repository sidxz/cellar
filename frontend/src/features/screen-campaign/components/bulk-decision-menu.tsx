"use client";

/**
 * BulkDecisionMenu — sets one decision on every currently-visible (filtered)
 * campaign result. Sits in the campaign toolbar above the grid.
 *
 * Visible = whatever passes the active CampaignFilters. So a chemist can
 * filter to "Hit" and click "Mark all Selected", or filter to "Non-hit"
 * and click "Mark all Rejected", etc. Without any filter, the action
 * targets every row — the confirm dialog spells out the count and target
 * decision so an accidental bulk overwrite is one click away from undo
 * (each decision is individually editable afterwards).
 */

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/shared/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { showSuccess, showError } from "@/shared/lib/toast";

import { useBulkSetResultDecisionsApiV1CampaignsCampaignIdResultsBulkDecisionPatch } from "@/shared/lib/api/campaigns/campaigns";

import type { CampaignResponse } from "../types";
import { rowPassesFilters, type CampaignFilters } from "./campaign-filter-bar";
import { campaignKeys } from "../hooks/use-campaigns";

type Decision = "selected" | "deferred" | "rejected";

const BUTTON_STYLE: Record<Decision, string> = {
  selected:
    "border-green-300 bg-green-50 text-green-800 hover:bg-green-100 dark:bg-green-950/40 dark:text-green-200 dark:hover:bg-green-900/60",
  deferred:
    "border-yellow-300 bg-yellow-50 text-yellow-800 hover:bg-yellow-100 dark:bg-yellow-950/40 dark:text-yellow-200 dark:hover:bg-yellow-900/60",
  rejected:
    "border-red-300 bg-red-50 text-red-800 hover:bg-red-100 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-900/60",
};

const VERB: Record<Decision, string> = {
  selected: "Select",
  deferred: "Defer",
  rejected: "Reject",
};

interface BulkDecisionMenuProps {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  readOnly: boolean;
}

export function BulkDecisionMenu({
  campaign,
  filters,
  readOnly,
}: BulkDecisionMenuProps) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<Decision | null>(null);

  // Filtered result ids — recomputed only when the inputs change.
  const visibleIds = useMemo(() => {
    return (campaign.results ?? [])
      .filter((r) => rowPassesFilters(r, filters))
      .map((r) => r.id);
  }, [campaign.results, filters]);

  const visibleCount = visibleIds.length;

  const mutation =
    useBulkSetResultDecisionsApiV1CampaignsCampaignIdResultsBulkDecisionPatch({
      mutation: {
        onSuccess: (data) => {
          const updated = data.updated_count;
          showSuccess(
            updated === 0
              ? "No rows changed (already at that decision)"
              : `Updated ${updated} ${updated === 1 ? "row" : "rows"}`,
          );
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : String(err);
          showError(`Bulk decision failed: ${msg}`);
        },
      },
    });

  if (readOnly) return null;

  function confirm() {
    if (!pending) return;
    mutation.mutate({
      campaignId: campaign.id,
      data: { result_ids: visibleIds, decision: pending, reason: null },
    });
    setPending(null);
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground">
        Bulk decision ({visibleCount} {visibleCount === 1 ? "row" : "rows"}):
      </span>
      {(["selected", "deferred", "rejected"] as Decision[]).map((d) => (
        <Button
          key={d}
          size="sm"
          variant="outline"
          disabled={visibleCount === 0 || mutation.isPending}
          onClick={() => setPending(d)}
          className={`h-7 px-2 text-xs capitalize ${BUTTON_STYLE[d]}`}
        >
          {d}
        </Button>
      ))}

      <AlertDialog open={pending !== null} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending ? `${VERB[pending]} ${visibleCount} ${visibleCount === 1 ? "row" : "rows"}?` : ""}
            </AlertDialogTitle>
            <AlertDialogDescription>
              This sets the decision to{" "}
              <span className="font-medium capitalize text-foreground">{pending}</span>{" "}
              on every row currently visible in the grid. Rows already at this
              decision are skipped. You can still edit individual rows
              afterwards — nothing is locked.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirm}>
              {pending ? `${VERB[pending]} ${visibleCount} rows` : ""}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
