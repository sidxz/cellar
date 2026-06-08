"use client";

import { Button } from "@/shared/components/ui/button";
import { Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useUpdateRun } from "../hooks/use-runs";
import type { Run } from "../types";

/**
 * Inline click-to-edit run notes for the summary header. Mirrors the campaign
 * `DescriptionRow` affordance: the text itself is the click target (no corner
 * pencil), switching to a textarea with explicit Save / Cancel. ⌘/Ctrl+Enter
 * saves and Escape cancels for keyboard-first chemists.
 *
 * Read-only viewers see plain text when notes exist, and nothing at all when
 * they don't — the line never reserves empty space.
 */
export function RunNotesLine({ run, canEdit }: { run: Run; canEdit: boolean }) {
  const update = useUpdateRun();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(run.notes ?? "");
  const ref = useRef<HTMLTextAreaElement | null>(null);

  // Re-sync the local draft when the canonical run notes change underneath us
  // (e.g. another mutation refetches the run) while we're not actively editing.
  useEffect(() => {
    if (!editing) setDraft(run.notes ?? "");
  }, [run.notes, editing]);

  useEffect(() => {
    if (editing && ref.current) {
      const ta = ref.current;
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
  }, [editing]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed === (run.notes ?? "").trim()) {
      setEditing(false);
      return;
    }
    update.mutate(
      { runId: run.id, data: { notes: trimmed === "" ? null : trimmed } },
      { onSuccess: () => setEditing(false) },
    );
  };

  const cancel = () => {
    setDraft(run.notes ?? "");
    setEditing(false);
  };

  if (editing) {
    const dirty = draft.trim() !== (run.notes ?? "").trim();
    return (
      <div className="mt-1.5 flex flex-col gap-2">
        <textarea
          ref={ref}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              commit();
            }
          }}
          rows={2}
          disabled={update.isPending}
          placeholder="Add notes about this run…"
          className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50"
        />
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={cancel}
            disabled={update.isPending}
          >
            Cancel
          </Button>
          <Button type="button" size="sm" onClick={commit} disabled={update.isPending || !dirty}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    );
  }

  const hasNotes = !!run.notes?.trim();
  if (!hasNotes && !canEdit) return null;

  if (!canEdit) {
    return <p className="mt-1.5 text-sm text-muted-foreground">{run.notes}</p>;
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      aria-label={hasNotes ? "Edit notes" : "Add notes"}
      className="group mt-1 -ml-1 inline-flex max-w-full items-start gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
    >
      <span
        className={
          hasNotes ? "text-sm text-muted-foreground" : "text-sm italic text-muted-foreground/60"
        }
      >
        {hasNotes ? run.notes : "Add notes…"}
      </span>
      <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground" />
    </button>
  );
}
