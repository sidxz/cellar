"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useWorkbench } from "../store/workbench-context";

interface WorkbenchBodyProps {
  /** Panel area (above the table). */
  plots: ReactNode;
  /** Data table (below the plots). */
  table: ReactNode;
  /** Filter rail content. */
  rail: ReactNode;
  /** The plot editor; while set it takes the rail's place at every width. */
  editor?: ReactNode;
}

/** The dashboard's <main> grows with the page and scrolls nothing, yet its overflow:auto would
 * hold every sticky child in place. Let it overflow: the viewport scrolls, and the rail, the
 * editor and the table header stick to it (as on the compound search page). */
const PAGE_SCROLLS = "main:has(.viz-workbench){overflow:visible}";

/** The frame below the header: the plots over the table, flowing with the page, and the
 * filter rail sticky beside them — a column from 1280 px, behind a "Filters (n)" tab below
 * that. The plot editor, while open, replaces the rail (which stays mounted, hidden). */
export function WorkbenchBody({ plots, table, rail, editor }: WorkbenchBodyProps) {
  const filterCount = useWorkbench((s) => s.filters.length);
  const [railOpen, setRailOpen] = useState(false);
  const tabRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const editing = Boolean(editor);
  // The overlay (below 1280 px) takes focus when it opens and gives it back when it closes.
  useEffect(() => {
    if (railOpen) closeRef.current?.focus();
  }, [railOpen]);
  const closeRail = () => {
    setRailOpen(false);
    tabRef.current?.focus();
  };
  // Plotly resizes on window resize only; the plots column just changed width.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when the editor opens or closes
  useEffect(() => {
    window.dispatchEvent(new Event("resize"));
  }, [editing]);
  return (
    <div className="viz-workbench flex items-start gap-3">
      <style>{PAGE_SCROLLS}</style>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="rounded-md border">{plots}</div>
        <div className="rounded-md border">{table}</div>
      </div>
      <button
        ref={tabRef}
        type="button"
        className={cn(
          "sticky top-2 shrink-0 rounded-md border px-1.5 py-3 text-xs font-medium [writing-mode:vertical-rl] hover:bg-accent xl:hidden",
          editing && "hidden",
        )}
        aria-expanded={railOpen}
        onClick={() => setRailOpen(true)}
      >
        Filters ({filterCount})
      </button>
      <aside
        aria-label="Filters"
        onKeyDown={(e) => {
          // Popovers inside handle (and mark) their own Escape first.
          if (railOpen && e.key === "Escape" && !e.defaultPrevented) closeRail();
        }}
        className={cn(
          "w-72 shrink-0 flex-col overflow-auto rounded-md border bg-background xl:sticky xl:inset-auto xl:top-2 xl:z-auto xl:flex xl:max-h-[calc(100dvh-1rem)] xl:shadow-none",
          // Below 1280 px: a drawer on the viewport's right edge, wherever the page is scrolled.
          railOpen ? "fixed inset-y-0 right-0 z-40 flex shadow-lg" : "hidden",
          editing && "hidden xl:hidden",
        )}
      >
        <div className="flex justify-end p-1 xl:hidden">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            ref={closeRef}
            aria-label="Close filters"
            onClick={closeRail}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {rail}
      </aside>
      {editing && (
        <aside
          aria-label="Edit plot"
          className="sticky top-2 flex h-[calc(100dvh-1rem)] w-80 shrink-0 flex-col overflow-hidden rounded-md border bg-background"
        >
          {editor}
        </aside>
      )}
    </div>
  );
}
