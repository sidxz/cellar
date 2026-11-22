"use client";

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/shared/components/ui/context-menu";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import type { CampaignResultResponse } from "../../types";

interface NotesCellProps {
  result: CampaignResultResponse;
  readOnly: boolean;
  /** Opens the note for editing; only offered when not ``readOnly``. */
  onEdit: () => void;
  /** Opens the note's history. */
  onHistory: () => void;
}

/** Anything saved -- a note, or the stamp a removal leaves -- has a history to show. */
export function noteTracked(r: CampaignResultResponse): boolean {
  return Boolean(r.notes?.trim() || r.notes_edited_by || r.notes_edited_at);
}

/**
 * NotesCell — the grid's Notes column: the note in full (scrolling when long), then who saved
 * it and when, and "N versions" when it has changed, which opens its history. Right-click
 * anywhere in the cell for Add/Edit note (editors) and Note history; an editor can also click
 * the note to edit it.
 */
export function NotesCell({ result, readOnly, onEdit, onHistory }: NotesCellProps) {
  const nameOf = useMemberNames();
  const notes = result.notes?.trim() ?? "";
  const versions = result.notes_version_count ?? 0;
  const tracked = noteTracked(result);
  const stamp = result.notes_edited_at
    ? [nameOf(result.notes_edited_by), new Date(result.notes_edited_at).toLocaleDateString()]
        .filter(Boolean)
        .join(" · ")
    : "";

  const text = notes ? (
    <span className="min-h-0 overflow-y-auto whitespace-pre-wrap break-words text-sm text-foreground [overflow-wrap:anywhere]">
      {notes}
    </span>
  ) : tracked ? (
    <span className="text-xs italic text-muted-foreground">Note removed</span>
  ) : (
    <span className="text-muted-foreground">—</span>
  );

  const content = (
    <div className="absolute inset-0 flex flex-col justify-center gap-0.5 px-2 py-2">
      {readOnly ? (
        text
      ) : (
        <button
          type="button"
          onClick={onEdit}
          aria-label={notes ? "Edit note" : "Add note"}
          className="flex min-h-0 flex-col text-left"
        >
          {text}
        </button>
      )}
      {(stamp || versions > 1) && (
        <span className="flex shrink-0 flex-wrap items-baseline gap-x-1 text-xs text-muted-foreground">
          {stamp}
          {versions > 1 && (
            <button
              type="button"
              onClick={onHistory}
              className="underline underline-offset-2 hover:text-foreground"
            >
              {stamp ? "· " : ""}
              {versions} versions
            </button>
          )}
        </span>
      )}
    </div>
  );

  if (readOnly && !tracked) return content;
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{content}</ContextMenuTrigger>
      <ContextMenuContent>
        {!readOnly && (
          <ContextMenuItem onSelect={onEdit}>{notes ? "Edit note…" : "Add note…"}</ContextMenuItem>
        )}
        {tracked && <ContextMenuItem onSelect={onHistory}>Note history…</ContextMenuItem>}
      </ContextMenuContent>
    </ContextMenu>
  );
}
