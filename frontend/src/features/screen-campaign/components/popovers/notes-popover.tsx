"use client";

/**
 * NotesPopover — edit the free-text notes on one campaign result.
 *
 * Save is *explicit*: typing never flushes. Save commits the notes in one
 * PATCH (empty text clears them to null); Cancel — and closing the popover
 * by clicking outside — discards local edits.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { showError } from "@/shared/lib/toast";

import { useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../../hooks/use-campaigns";
import type { CampaignResultResponse } from "../../types";

export interface NotesPopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  onClose: () => void;
}

export function NotesPopover({ campaignId, result, onClose }: NotesPopoverProps) {
  const initial = result.notes ?? "";
  const [notes, setNotes] = useState(initial);

  const qc = useQueryClient();
  const mutation = useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
      onError: (err) => {
        const msg = err instanceof Error ? err.message : String(err);
        showError(`Couldn't save notes: ${msg}`);
      },
    },
  });

  const dirty = notes !== initial;

  function onSave() {
    if (!dirty) {
      onClose();
      return;
    }
    mutation.mutate({
      campaignId,
      resultId: result.id,
      data: { notes: notes.trim() ? notes.trim() : null },
    });
  }

  return (
    <div className="space-y-3 p-1">
      <div className="space-y-1">
        <Label htmlFor={`notes-${result.id}`} className="text-xs">
          Notes
        </Label>
        <Textarea
          id={`notes-${result.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Freeform notes…"
          rows={4}
          className="text-sm"
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSave} disabled={mutation.isPending || !dirty}>
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
