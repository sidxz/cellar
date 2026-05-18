"use client";

import { GitFork, LayoutGrid, Table } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { ViewMode } from "../../lib/use-view-mode";

export interface ViewModeToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
}

/**
 * Three-segment view-mode toggle: List | Grid | Scaffold.
 *
 * Icon-only was confusing — chemists asked for text labels. Names chosen
 * to match how chemists actually talk about these surfaces:
 *   List     = the columnar AG Grid table (rows of compound records)
 *   Grid     = the card grid (visual structure tiles)
 *   Scaffold = the scaffold-tree split-pane (chemotypes left, mols right)
 *
 * Labels hide on very narrow viewports (< sm) to keep the toolbar compact;
 * icon + aria-label remain.
 */
export function ViewModeToggle({ mode, onChange, className }: ViewModeToggleProps) {
  return (
    <div
      className={cn("inline-flex items-center gap-1 rounded-md border border-input p-0.5", className)}
      role="group"
    >
      <Button
        type="button"
        variant={mode === "table" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2 gap-1.5"
        aria-label="List view"
        aria-pressed={mode === "table"}
        onClick={() => mode !== "table" && onChange("table")}
      >
        <Table className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">List</span>
      </Button>
      <Button
        type="button"
        variant={mode === "cards" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2 gap-1.5"
        aria-label="Grid view"
        aria-pressed={mode === "cards"}
        onClick={() => mode !== "cards" && onChange("cards")}
      >
        <LayoutGrid className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">Grid</span>
      </Button>
      <Button
        type="button"
        variant={mode === "scaffold-tree" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2 gap-1.5"
        aria-label="Scaffold view"
        aria-pressed={mode === "scaffold-tree"}
        onClick={() => mode !== "scaffold-tree" && onChange("scaffold-tree")}
      >
        <GitFork className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">Scaffold</span>
      </Button>
    </div>
  );
}
