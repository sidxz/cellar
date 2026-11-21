"use client";

/**
 * NotesPopover — read or edit the note on one campaign result, and see its history.
 *
 * Save is *explicit*: typing never flushes. Save sends the note together with the
 * note as it was opened, so a colleague's newer note is never overwritten blind:
 * the server refuses with a 409, the popover shows their note, keeps your text,
 * and a second Save replaces theirs knowingly. Cancel (or clicking outside)
 * discards local edits. ``readOnly`` shows the note and its history only.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { ApiError, isStaleEdit } from "@/shared/lib/api/custom-instance";
import type { ResultNoteResponse } from "@/shared/lib/api/model";
import { showError } from "@/shared/lib/toast";

import { campaignKeys, useResultNoteHistory } from "../../hooks/use-campaigns";
import type { CampaignResponse, CampaignResultResponse } from "../../types";

export interface NotesPopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  onClose: () => void;
  readOnly?: boolean;
}

/** The server's rule: trimmed, and blank means no note. */
const normalize = (text: string | null | undefined): string | null => text?.trim() || null;

/** "by <name> · <date>", as the QC cells word it. */
export function noteStamp(name: string, at: string): string {
  return `by ${name} · ${new Date(at).toLocaleDateString()}`;
}

function NoteHistory({ campaignId, resultId }: { campaignId: string; resultId: string }) {
  const nameOf = useMemberNames();
  const { data, isLoading } = useResultNoteHistory(campaignId, resultId);
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>;
  const versions = data?.versions ?? [];
  if (versions.length === 0) {
    return <p className="text-xs text-muted-foreground">No earlier versions.</p>;
  }
  return (
    <ol className="max-h-60 space-y-2 overflow-y-auto">
      {versions.map((v, i) => (
        // Versions have no id and never reorder: newest first, append-only.
        // biome-ignore lint/suspicious/noArrayIndexKey: see above
        <li key={i} className="border-l-2 pl-2 text-xs">
          {v.notes ? (
            <p className="whitespace-pre-wrap">{v.notes}</p>
          ) : (
            <p className="italic text-muted-foreground">Note removed</p>
          )}
          <p className="text-[10px] text-muted-foreground">
            {v.edited_at
              ? noteStamp(nameOf(v.edited_by), v.edited_at)
              : "Before edits were tracked"}
          </p>
        </li>
      ))}
    </ol>
  );
}

export function NotesPopover({ campaignId, result, onClose, readOnly = false }: NotesPopoverProps) {
  const nameOf = useMemberNames();
  const [notes, setNotes] = useState(result.notes ?? "");
  // The note this edit is based on, exactly as the server holds it (the server
  // normalizes both sides; a browser-trimmed copy can differ). A 409 moves it to
  // the colleague's note.
  const [base, setBase] = useState<string | null>(result.notes ?? null);
  const [stale, setStale] = useState<ResultNoteResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const qc = useQueryClient();
  const mutation = useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch({
    mutation: {
      onSuccess: (saved) => {
        // Put the saved note on the row now: reopening it before the refetch lands
        // must not look like a colleague's change. The detail key prefixes the
        // history key, so both refetch.
        qc.setQueryData<CampaignResponse>(campaignKeys.detail(campaignId), (old) =>
          old
            ? {
                ...old,
                results: old.results.map((r) => (r.id === result.id ? { ...r, ...saved } : r)),
              }
            : old,
        );
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
      onError: (err) => {
        if (isStaleEdit(err) && err instanceof ApiError) {
          const current = (err.body as { current?: ResultNoteResponse }).current ?? null;
          setStale(current);
          setBase(current?.notes ?? null);
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
          return;
        }
        const msg = err instanceof Error ? err.message : String(err);
        showError(`Couldn't save notes: ${msg}`);
      },
    },
  });

  const dirty = normalize(notes) !== normalize(base);

  function onSave() {
    if (!dirty) {
      onClose();
      return;
    }
    mutation.mutate({
      campaignId,
      resultId: result.id,
      data: { notes: normalize(notes), expected_notes: base },
    });
  }

  const historyToggle = (
    <Button variant="ghost" size="sm" onClick={() => setShowHistory((s) => !s)}>
      History
    </Button>
  );

  if (readOnly) {
    return (
      <div className="space-y-3 p-1">
        {result.notes && <p className="whitespace-pre-wrap text-sm">{result.notes}</p>}
        <div className="flex justify-start">{historyToggle}</div>
        {showHistory && <NoteHistory campaignId={campaignId} resultId={result.id} />}
      </div>
    );
  }

  return (
    <div className="space-y-3 p-1">
      {stale && (
        <div className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs dark:border-amber-700 dark:bg-amber-950">
          <p className="font-medium">Someone changed this note since you opened it</p>
          {stale.notes ? (
            <p className="whitespace-pre-wrap">{stale.notes}</p>
          ) : (
            <p className="italic text-muted-foreground">Note removed</p>
          )}
          {stale.notes_edited_at && (
            <p className="text-[10px] text-muted-foreground">
              {noteStamp(nameOf(stale.notes_edited_by), stale.notes_edited_at)}
            </p>
          )}
          <p>Save again to replace it with yours.</p>
        </div>
      )}

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

      <div className="flex justify-between gap-2">
        {historyToggle}
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSave} disabled={mutation.isPending || !dirty}>
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {showHistory && <NoteHistory campaignId={campaignId} resultId={result.id} />}
    </div>
  );
}
