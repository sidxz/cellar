"use client";

/**
 * StageOverridePopover — force one result's outcome for one hit stage.
 *
 * Shows the stage's current outcome for this result plus the checks that
 * didn't pass, then lets the chemist promote it to a hit or demote it to a
 * miss with a required reason (21 CFR-style: an override always carries its
 * rationale). Saving is *explicit* — typing a reason changes nothing until a
 * button is pressed — and an existing override can be cleared, handing the
 * row back to the evaluator.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { showError, showSuccess } from "@/shared/lib/toast";

import {
  useClearStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverrideDelete,
  useSetStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverridePut,
} from "@/shared/lib/api/campaigns/campaigns";

import { campaignKeys } from "../../hooks/use-campaigns";
import type {
  CampaignResultResponse,
  CampaignStageResponse,
  CheckVerdict,
  StageOutcome,
  StageOutcomeResponse,
} from "../../types";

const OUTCOME_LABELS: Record<StageOutcome, string> = {
  hit: "Hit",
  miss: "Miss",
  untested: "Untested",
  not_in_stage: "Not in stage",
};

export interface StageOverridePopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  stage: CampaignStageResponse;
  /** This result's outcome for `stage` — undefined when it carries none. */
  outcome: StageOutcomeResponse | undefined;
  /** Readout labels by channel id — never show channel UUIDs. */
  channelLabelById: ReadonlyMap<string, string>;
  onClose: () => void;
}

export function StageOverridePopover({
  campaignId,
  result,
  stage,
  outcome,
  channelLabelById,
  onClose,
}: StageOverridePopoverProps) {
  const [reason, setReason] = useState(outcome?.override_reason ?? "");

  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
  const onError = (err: unknown) => {
    showError(`Couldn't save override: ${err instanceof Error ? err.message : String(err)}`);
  };

  const setMutation =
    useSetStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverridePut({
      mutation: {
        onSuccess: (_data, vars) => {
          void invalidate();
          showSuccess(vars.data.outcome === "hit" ? "Promoted to hit" : "Demoted to miss");
          onClose();
        },
        onError,
      },
    });

  const clearMutation =
    useClearStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverrideDelete({
      mutation: {
        onSuccess: () => {
          void invalidate();
          showSuccess("Override cleared");
          onClose();
        },
        onError,
      },
    });

  const busy = setMutation.isPending || clearMutation.isPending;
  const current = (outcome?.outcome ?? "not_in_stage") as StageOutcome;
  const overridden = outcome?.overridden ?? false;
  const reasonOk = reason.trim().length > 0;

  // Only the checks worth explaining — a passing check is why the row is
  // where it is, the failing/untested ones are why it isn't a hit.
  const problems = (outcome?.checks ?? []).filter((c) => c.verdict !== "pass");

  function force(next: "hit" | "miss") {
    if (!reasonOk) return;
    setMutation.mutate({
      campaignId,
      resultId: result.id,
      stageId: stage.id,
      data: { outcome: next, reason: reason.trim() },
    });
  }

  return (
    <div className="space-y-3 p-1">
      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground uppercase font-medium">{stage.name}</Label>
        <p className="text-sm">
          <span className="font-medium">{OUTCOME_LABELS[current]}</span>
          {overridden && <span className="text-muted-foreground"> · overridden</span>}
        </p>
        {overridden && outcome?.override_reason && (
          <p className="text-xs text-muted-foreground italic">{outcome.override_reason}</p>
        )}
      </div>

      {problems.length > 0 && (
        <ul className="space-y-0.5 rounded-md border bg-muted/40 px-2 py-1.5">
          {problems.map((c) => (
            <li key={c.channel_id} className="text-xs">
              <span className="font-medium">
                {channelLabelById.get(c.channel_id) ?? "Unknown readout"}
              </span>
              <span className="text-muted-foreground"> — {c.verdict as CheckVerdict}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-1">
        <Label htmlFor={`stage-reason-${result.id}`} className="text-xs">
          Reason <span className="text-destructive">*</span>
        </Label>
        <Textarea
          id={`stage-reason-${result.id}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why does this compound belong in / out of this stage?"
          rows={2}
          className="text-sm"
        />
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        {overridden && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() =>
              clearMutation.mutate({ campaignId, resultId: result.id, stageId: stage.id })
            }
          >
            Clear override
          </Button>
        )}
        {(current !== "miss" || overridden) && (
          <Button
            variant="outline"
            size="sm"
            disabled={busy || !reasonOk}
            onClick={() => force("miss")}
          >
            Demote to miss
          </Button>
        )}
        {(current !== "hit" || overridden) && (
          <Button size="sm" disabled={busy || !reasonOk} onClick={() => force("hit")}>
            Promote to hit
          </Button>
        )}
      </div>
    </div>
  );
}
