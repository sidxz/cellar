"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useState } from "react";
import type { CampaignResultResponse } from "../../types";
import { NotesPopover } from "../popovers/notes-popover";

interface NotesCellProps {
  campaignId: string;
  result: CampaignResultResponse;
  readOnly: boolean;
}

/**
 * NotesCell — the grid's Notes column. Shows the notes clamped to 3 lines
 * (full text in the title tooltip); in a draft campaign the whole cell is a
 * button that opens <NotesPopover> for an explicit edit-and-save.
 */
export function NotesCell({ campaignId, result, readOnly }: NotesCellProps) {
  const [open, setOpen] = useState(false);
  const notes = result.notes?.trim() ?? "";

  const body = notes ? (
    <p className="line-clamp-3 text-[11px] leading-tight text-muted-foreground" title={notes}>
      {notes}
    </p>
  ) : readOnly ? null : (
    <span className="text-[11px] italic text-muted-foreground/70">Add note</span>
  );

  if (readOnly) {
    return <div className="max-w-[200px] py-1 text-left">{body}</div>;
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="max-w-[200px] py-1 text-left" aria-label="Edit notes">
          {body}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <NotesPopover campaignId={campaignId} result={result} onClose={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
