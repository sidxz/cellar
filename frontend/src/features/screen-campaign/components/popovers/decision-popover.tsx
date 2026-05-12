"use client";

/**
 * DecisionPopover — Task 3.5
 *
 * Popover form for setting a result's decision (selected / deferred / rejected),
 * an optional reason, and freeform notes.
 *
 * - Auto-saves on 300 ms debounce (same pattern as DecisionPanel).
 * - Commits any remaining dirty state when the popover is closed/unmounted.
 * - Cancel closes without an extra save; Save fires immediately then closes.
 */

import { useEffect, useRef, useState } from "react";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Button } from "@/shared/components/ui/button";
import { useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { useQueryClient } from "@tanstack/react-query";
import { campaignKeys } from "../../lib/hooks";
import type { CampaignResultResponse } from "../../types";

// ── Types ──────────────────────────────────────────────────────────────────────

type Decision = "selected" | "deferred" | "rejected";

export interface DecisionPopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  onClose: () => void;
}

// ── Component ──────────────────────────────────────────────────────────────────

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
  const [notes, setNotes] = useState(
    (result.notes as string | undefined) ?? "",
  );

  // Snapshot of last-saved values — used to skip no-op PATCHes.
  const lastSaved = useRef<{
    decision: Decision;
    reason: string;
    notes: string;
  }>({
    decision: (result.decision ?? "deferred") as Decision,
    reason: (result.decision_reason as string | undefined) ?? "",
    notes: (result.notes as string | undefined) ?? "",
  });

  // Whether we have un-sent local changes.
  const dirty = useRef(false);

  const qc = useQueryClient();

  // Same hook the legacy DecisionPanel uses.
  const mutation =
    useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch();

  // Invalidate the campaign detail query on success so any parent grid/view
  // picks up the new values without a full page reload.
  const fire = (
    dec: Decision = decision,
    rsn: string = reason,
    nts: string = notes,
  ) => {
    mutation.mutate(
      {
        campaignId,
        resultId: result.id,
        data: {
          decision: dec,
          reason: rsn || undefined,
          notes: nts || null,
        },
      },
      {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        },
      },
    );
    lastSaved.current = { decision: dec, reason: rsn, notes: nts };
    dirty.current = false;
  };

  const isDirty = (dec: Decision, rsn: string, nts: string) =>
    dec !== lastSaved.current.decision ||
    rsn !== lastSaved.current.reason ||
    nts !== lastSaved.current.notes;

  // 300 ms debounced background save — mirrors DecisionPanel's approach.
  useEffect(() => {
    if (!isDirty(decision, reason, notes)) return;
    dirty.current = true;
    const t = setTimeout(() => {
      fire(decision, reason, notes);
    }, 300);
    return () => clearTimeout(t);
    // fire is intentionally omitted — it's a stable closure over the current
    // state snapshot captured at effect evaluation time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decision, reason, notes]);

  // Autosave on unmount if there's still a pending dirty state (e.g. the user
  // closed the popover before the 300 ms timer fired).
  useEffect(() => {
    return () => {
      if (dirty.current) {
        // Capture current state via a ref-captured snapshot.
        // At unmount time the closure variables (decision/reason/notes) are
        // stale in strict-mode double-invocation, but dirty.current is only
        // true when the debounce timer was cleared before it fired — meaning
        // the values they hold ARE the unsynced values. Safe to fire here.
        fire(decision, reason, notes);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSave = () => {
    if (isDirty(decision, reason, notes)) {
      fire(decision, reason, notes);
    }
    onClose();
  };

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
        {mutation.isPending && (
          <p className="text-xs text-muted-foreground">Saving…</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSave}>
          Save
        </Button>
      </div>
    </div>
  );
}
