"use client";

/**
 * StageBulkMenu — forces (or clears) one hit stage's verdict for the ticked
 * campaign results in a single save. Renders only its controls: the grid's
 * bulk bar holds it beside the QC menu. The usual flow on a manual stage is:
 * filter to Pending, tick the keepers (or select all visible), then Mark hit.
 *
 * Marking hit or miss carries a required reason (21 CFR-style: an override always
 * records its rationale); "Clear overrides" sends `outcome: null` and hands
 * the rows back to the evaluator, so it needs none.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

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
import { selectionText } from "./grid/selection-text";

type BulkAction = "hit" | "miss" | "clear";

const ACTION_LABEL: Record<BulkAction, string> = {
  hit: "Mark hit…",
  miss: "Mark miss…",
  clear: "Clear overrides",
};

/** The wire value each action sends — `null` clears the override. */
const ACTION_OUTCOME: Record<BulkAction, "hit" | "miss" | null> = {
  hit: "hit",
  miss: "miss",
  clear: null,
};

interface StageBulkMenuProps {
  campaign: CampaignResponse;
  /** The ticked rows: what every action acts on. */
  resultIds: string[];
  /** How many of them the filters hide, said in the confirmation. */
  hiddenCount: number;
  /** Selected hit stage — the menu renders nothing for "All". */
  selectedStageId: string | null;
  readOnly: boolean;
}

export function StageBulkMenu({
  campaign,
  resultIds,
  hiddenCount,
  selectedStageId,
  readOnly,
}: StageBulkMenuProps) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<BulkAction | null>(null);
  const [reason, setReason] = useState("");
  const count = resultIds.length;

  const mutation = useSetStageOverridesApiV1CampaignsCampaignIdStagesStageIdOverridesPut({
    mutation: {
      onSuccess: (_data, vars) => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        const n = vars.data.result_ids.length;
        showSuccess(
          vars.data.outcome === null
            ? `Cleared overrides on ${n} ${n === 1 ? "row" : "rows"}`
            : `Marked ${n} ${n === 1 ? "row" : "rows"} ${vars.data.outcome}`,
        );
      },
      onError: (err) => {
        showError(`Bulk override failed: ${err instanceof Error ? err.message : String(err)}`);
      },
    },
  });

  if (readOnly || !selectedStageId) return null;

  const needsReason = pending === "hit" || pending === "miss";
  const scope = `${count} selected ${count === 1 ? "row" : "rows"}`;
  const stage = (campaign.stages ?? []).find((s) => s.id === selectedStageId);
  // A hand-picked stage has no selection criteria to override.
  const manual = stage?.kind === "manual";
  const plural = pending === "hit" ? "hits" : "misses";
  const title =
    pending === "clear"
      ? `Clear overrides for ${scope}?`
      : manual
        ? `Mark ${scope} ${pending}?`
        : `Override the selection criteria for ${scope}?`;
  const description =
    pending === "clear"
      ? manual
        ? "They go back to pending at this hand-picked stage."
        : "The selection criteria decide their outcomes again."
      : manual
        ? `They count as ${plural} at ${stage?.name ?? "this stage"} until you change them.`
        : `Mark them ${pending} at ${stage?.name ?? "this stage"}, whatever its selection criteria say. They stay ${pending} until the override is cleared; you can still change a single row.`;
  const confirmationLabel =
    pending === "clear"
      ? `Clear ${count} ${count === 1 ? "override" : "overrides"}`
      : manual
        ? `Mark ${count} ${pending}`
        : `Override and mark ${count} ${pending}`;
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
        result_ids: resultIds,
        outcome: ACTION_OUTCOME[pending],
        reason: needsReason ? reason.trim() : null,
      },
    });
    setPending(null);
  }

  return (
    <>
      {(["hit", "miss", "clear"] as BulkAction[]).map((a) => (
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
            <AlertDialogTitle>{pending && title}</AlertDialogTitle>
            <AlertDialogDescription>
              {pending && description}
              {hiddenCount > 0 && ` ${selectionText(count, hiddenCount)}.`}
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
                placeholder={
                  manual
                    ? `Why these compounds are ${plural}`
                    : `Why these compounds are ${plural} despite the selection criteria`
                }
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
              {pending && confirmationLabel}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
