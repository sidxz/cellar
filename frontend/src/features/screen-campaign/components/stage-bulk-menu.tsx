"use client";

/**
 * StageBulkMenu — forces (or clears) one hit stage's verdict for every
 * currently-visible campaign result in a single save. Sits in the campaign
 * toolbar above the grid, next to the filter chips it reads from.
 *
 * "Visible" is whatever `rowPassesFilters` lets through for the selected
 * stage — the same predicate the grid's external filter uses, so what the
 * chemist sees is exactly what the gesture touches. The usual flow on a
 * manual stage is: filter to Pending, then Promote the keepers.
 *
 * Promote/demote carry a required reason (21 CFR-style: an override always
 * records its rationale); "Clear overrides" sends `outcome: null` and hands
 * the rows back to the evaluator, so it needs none.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useSetStageOverridesApiV1CampaignsCampaignIdStagesStageIdOverridesPut } from "@/shared/lib/api/campaigns/campaigns";
import { showError, showSuccess } from "@/shared/lib/toast";

import { campaignKeys } from "../hooks/use-campaigns";
import type { CampaignResponse } from "../types";
import { type CampaignFilters, rowPassesFilters } from "./campaign-filter-bar";

type BulkAction = "promote" | "demote" | "clear";

const ACTION_LABEL: Record<BulkAction, string> = {
  promote: "Promote",
  demote: "Demote",
  clear: "Clear overrides",
};

/** The wire value each action sends — `null` clears the override. */
const ACTION_OUTCOME: Record<BulkAction, "hit" | "miss" | null> = {
  promote: "hit",
  demote: "miss",
  clear: null,
};

interface StageBulkMenuProps {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  /** Selected hit stage — the menu renders nothing for "All". */
  selectedStageId: string | null;
  readOnly: boolean;
}

export function StageBulkMenu({
  campaign,
  filters,
  selectedStageId,
  readOnly,
}: StageBulkMenuProps) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<BulkAction | null>(null);
  const [reason, setReason] = useState("");

  const visibleIds = useMemo(
    () =>
      (campaign.results ?? [])
        .filter((r) => rowPassesFilters(r, filters, selectedStageId))
        .map((r) => r.id),
    [campaign.results, filters, selectedStageId],
  );
  const count = visibleIds.length;

  const mutation = useSetStageOverridesApiV1CampaignsCampaignIdStagesStageIdOverridesPut({
    mutation: {
      onSuccess: (_data, vars) => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        const n = vars.data.result_ids.length;
        showSuccess(
          vars.data.outcome === null
            ? `Cleared overrides on ${n} ${n === 1 ? "row" : "rows"}`
            : `${vars.data.outcome === "hit" ? "Promoted" : "Demoted"} ${n} ${n === 1 ? "row" : "rows"}`,
        );
      },
      onError: (err) => {
        showError(`Bulk override failed: ${err instanceof Error ? err.message : String(err)}`);
      },
    },
  });

  if (readOnly || !selectedStageId) return null;

  const needsReason = pending === "promote" || pending === "demote";
  const reasonOk = !needsReason || reason.trim().length > 0;

  function open(action: BulkAction) {
    setReason("");
    setPending(action);
  }

  function confirm() {
    if (!pending || !selectedStageId || !reasonOk) return;
    mutation.mutate({
      campaignId: campaign.id,
      stageId: selectedStageId,
      data: {
        result_ids: visibleIds,
        outcome: ACTION_OUTCOME[pending],
        reason: needsReason ? reason.trim() : null,
      },
    });
    setPending(null);
  }

  return (
    <div className="flex items-center gap-1.5 border-b bg-muted/10 px-3 py-1.5">
      <span className="text-xs text-muted-foreground">
        Bulk ({count} visible {count === 1 ? "row" : "rows"}):
      </span>
      {(["promote", "demote", "clear"] as BulkAction[]).map((a) => (
        <Button
          key={a}
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
          disabled={count === 0 || mutation.isPending}
          onClick={() => open(a)}
        >
          {ACTION_LABEL[a]}
        </Button>
      ))}

      <AlertDialog open={pending !== null} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending ? `${ACTION_LABEL[pending]} ${count} ${count === 1 ? "row" : "rows"}?` : ""}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending === "clear"
                ? "This drops the manual override on every row currently visible in the grid, handing them back to the stage's own evaluation."
                : "This forces the outcome on every row currently visible in the grid. Individual rows can still be changed afterwards — nothing is locked."}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {needsReason && (
            <div className="space-y-1">
              <Label htmlFor="bulk-stage-reason" className="text-xs">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="bulk-stage-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why do these compounds belong in / out of this stage?"
                rows={2}
                className="text-sm"
              />
            </div>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {/* Not AlertDialogAction: it closes the dialog on click regardless
                of the handler, which would discard an empty-reason attempt
                instead of keeping the chemist in the form. */}
            <Button size="sm" disabled={!reasonOk} onClick={confirm}>
              {pending ? `${ACTION_LABEL[pending]} ${count} ${count === 1 ? "row" : "rows"}` : ""}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
