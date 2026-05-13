"use client";

/**
 * DecisionPopover — set a result's decision (selected / deferred / rejected),
 * an optional reason, and freeform notes.
 *
 * Save is *explicit*: clicking a radio button no longer flushes the decision
 * — the chemist gets time to type a reason/notes first. Save commits the
 * full triple in one PATCH; Cancel (and closing the popover by clicking
 * outside) discards local edits.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Button } from "@/shared/components/ui/button";
import { showError } from "@/shared/lib/toast";

import { useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../../hooks/use-campaigns";
import type { CampaignResultResponse } from "../../types";

type Decision = "selected" | "deferred" | "rejected";

export interface DecisionPopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  onClose: () => void;
}

export function DecisionPopover({
  campaignId,
  result,
  onClose,
}: DecisionPopoverProps) {
  const [decision, setDecision] = useState<Decision>(
    (result.decision ?? "deferred") as Decision,
  );
  const [reason, setReason] = useState(
    (result.decision_reason as string | undefined) ?? "",
  );
  const [notes, setNotes] = useState((result.notes as string | undefined) ?? "");

  const qc = useQueryClient();
  const mutation =
    useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch({
      mutation: {
        onSuccess: () => {
          void qc.invalidateQueries({
            queryKey: campaignKeys.detail(campaignId),
          });
          onClose();
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : String(err);
          showError(`Couldn't save decision: ${msg}`);
        },
      },
    });

  const initial = {
    decision: (result.decision ?? "deferred") as Decision,
    reason: (result.decision_reason as string | undefined) ?? "",
    notes: (result.notes as string | undefined) ?? "",
  };
  const dirty =
    decision !== initial.decision ||
    reason !== initial.reason ||
    notes !== initial.notes;

  function onSave() {
    if (!dirty) {
      onClose();
      return;
    }
    mutation.mutate({
      campaignId,
      resultId: result.id,
      data: {
        decision,
        reason: reason.trim() ? reason.trim() : undefined,
        notes: notes.trim() ? notes : null,
      },
    });
  }

  return (
    <div className="space-y-3 p-1">
      {/* Decision radio */}
      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground uppercase font-medium">
          Decision
        </Label>
        <RadioGroup
          value={decision}
          onValueChange={(v) => setDecision(v as Decision)}
          className="mt-1 space-y-1.5"
        >
          {(
            [
              { value: "selected", label: "Selected", color: "text-green-700" },
              { value: "deferred", label: "Deferred", color: "text-yellow-700" },
              { value: "rejected", label: "Rejected", color: "text-red-700" },
            ] as const
          ).map((opt) => (
            <div key={opt.value} className="flex items-center gap-2">
              <RadioGroupItem
                value={opt.value}
                id={`dec-${result.id}-${opt.value}`}
              />
              <Label
                htmlFor={`dec-${result.id}-${opt.value}`}
                className={`cursor-pointer font-medium ${opt.color}`}
              >
                {opt.label}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      {/* Reason */}
      <div className="space-y-1">
        <Label htmlFor={`dec-reason-${result.id}`} className="text-xs">
          Reason (optional)
        </Label>
        <Textarea
          id={`dec-reason-${result.id}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why was this decision made?"
          rows={2}
          className="text-sm"
        />
      </div>

      {/* Notes */}
      <div className="space-y-1">
        <Label htmlFor={`dec-notes-${result.id}`} className="text-xs">
          Notes
        </Label>
        <Textarea
          id={`dec-notes-${result.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Freeform notes…"
          rows={3}
          className="text-sm"
        />
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={onSave}
          disabled={mutation.isPending || !dirty}
        >
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
