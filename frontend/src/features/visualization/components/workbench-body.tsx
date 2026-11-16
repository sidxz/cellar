"use client";

import { Button } from "@/shared/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useWorkbench } from "../store/workbench-context";

interface WorkbenchBodyProps {
  /** Panel area (above the split). */
  plots: ReactNode;
  /** Data table (below the split). */
  table: ReactNode;
  /** Filter rail content. */
  rail: ReactNode;
  /** The plot editor; while set it takes the rail's place at every width. */
  editor?: ReactNode;
}

/** The frame below the header: plots over the table in a resizable split, and the filter
 * rail beside them — a column from 1280 px, behind a "Filters (n)" tab below that. The plot
 * editor, while open, replaces the rail (which stays mounted, hidden). */
export function WorkbenchBody({ plots, table, rail, editor }: WorkbenchBodyProps) {
  const filterCount = useWorkbench((s) => s.filters.length);
  const [railOpen, setRailOpen] = useState(false);
  const editing = Boolean(editor);
  // Plotly resizes on window resize only; the plots column just changed width.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when the editor opens or closes
  useEffect(() => {
    window.dispatchEvent(new Event("resize"));
  }, [editing]);
  return (
    <div className="relative flex min-h-0 flex-1 gap-3">
      <ResizablePanelGroup orientation="vertical" className="min-w-0 flex-1 rounded-md border">
        <ResizablePanel defaultSize="60%" minSize="20%">
          <div className="h-full overflow-auto">{plots}</div>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize="40%" minSize="15%">
          <div className="h-full overflow-auto">{table}</div>
        </ResizablePanel>
      </ResizablePanelGroup>
      <button
        type="button"
        className={cn(
          "shrink-0 rounded-md border px-1.5 py-3 text-xs font-medium [writing-mode:vertical-rl] hover:bg-accent xl:hidden",
          editing && "hidden",
        )}
        aria-expanded={railOpen}
        onClick={() => setRailOpen(true)}
      >
        Filters ({filterCount})
      </button>
      <aside
        aria-label="Filters"
        className={cn(
          "w-72 shrink-0 flex-col overflow-auto rounded-md border bg-background xl:static xl:flex xl:shadow-none",
          railOpen ? "absolute inset-y-0 right-0 z-20 flex shadow-lg" : "hidden",
          editing && "hidden xl:hidden",
        )}
      >
        <div className="flex justify-end p-1 xl:hidden">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label="Close filters"
            onClick={() => setRailOpen(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {rail}
      </aside>
      {editing && (
        <aside
          aria-label="Edit plot"
          className="flex w-80 shrink-0 flex-col overflow-hidden rounded-md border bg-background"
        >
          {editor}
        </aside>
      )}
    </div>
  );
}
