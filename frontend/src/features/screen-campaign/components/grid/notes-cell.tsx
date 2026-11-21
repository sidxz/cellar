"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { useState } from "react";
import type { CampaignResultResponse } from "../../types";
import { NotesPopover, noteStamp } from "../popovers/notes-popover";

interface NotesCellProps {
  campaignId: string;
  result: CampaignResultResponse;
  readOnly: boolean;
}

/**
 * NotesCell — the grid's Notes column. Shows the note clamped to 3 lines (full
 * text in the title tooltip) with who saved it and when underneath. For an
 * editor the whole cell is a button that opens <NotesPopover> for an explicit
 * edit-and-save, on any campaign status; read-only, a cell with a note (or a
 * removed one) opens the note's history instead.
 */
export function NotesCell({ campaignId, result, readOnly }: NotesCellProps) {
  const [open, setOpen] = useState(false);
  const nameOf = useMemberNames();
  const notes = result.notes?.trim() ?? "";
  const versions = result.notes_version_count ?? 0;
  const versionsSuffix = versions > 1 ? ` · ${versions} versions` : "";
  // A removed note still has history: say so rather than look like an empty row.
  const removed = !notes && (versions > 0 || Boolean(result.notes_edited_at));

  const body = notes ? (
    <>
      <p className="line-clamp-3 text-[11px] leading-tight text-muted-foreground" title={notes}>
        {notes}
      </p>
      {result.notes_edited_at && (
        <p className="text-[10px] leading-tight text-muted-foreground/70">
          {noteStamp(nameOf(result.notes_edited_by), result.notes_edited_at)}
          {versionsSuffix}
        </p>
      )}
    </>
  ) : (
    <>
      {!readOnly && <span className="text-[11px] italic text-muted-foreground/70">Add note</span>}
      {removed && (
        <p className="text-[10px] italic leading-tight text-muted-foreground/70">
          Note removed{versionsSuffix}
        </p>
      )}
    </>
  );

  if (readOnly && !notes && !removed) {
    return <div className="max-w-[200px] py-1 text-left" />;
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="max-w-[200px] py-1 text-left"
          aria-label={readOnly ? "Note history" : "Edit notes"}
        >
          {body}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <NotesPopover
          campaignId={campaignId}
          result={result}
          onClose={() => setOpen(false)}
          readOnly={readOnly}
        />
      </PopoverContent>
    </Popover>
  );
}
