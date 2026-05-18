"use client";

import { ChartScatter, GitFork, LayoutGrid, Table } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { ViewMode } from "../../lib/use-view-mode";

export interface ViewModeToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
  /**
   * Set of view modes that should be rendered as disabled (still visible but
   * not clickable). Callers use this for modes that require a minimum data
   * threshold (e.g. Cluster requires ≥ 10 molecules).
   */
  disabledModes?: Set<ViewMode>;
}

/**
 * Four-segment view-mode toggle: List | Grid | Scaffold | Cluster.
 *
 * Icon-only was confusing — chemists asked for text labels. Names chosen
 * to match how chemists actually talk about these surfaces:
 *   List     = the columnar AG Grid table (rows of compound records)
 *   Grid     = the card grid (visual structure tiles)
 *   Scaffold = the scaffold-tree split-pane (chemotypes left, mols right)
 *   Cluster  = the UMAP cluster map (scatter plot + lasso → save-as-collection)
 *
 * Labels hide on very narrow viewports (< sm) to keep the toolbar compact;
 * icon + aria-label remain.
 */
export function ViewModeToggle({ mode, onChange, className, disabledModes }: ViewModeToggleProps) {
  const isDisabled = (m: ViewMode) => disabledModes?.has(m) ?? false;

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
        disabled={isDisabled("table")}
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
        disabled={isDisabled("cards")}
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
        disabled={isDisabled("scaffold-tree")}
        onClick={() => mode !== "scaffold-tree" && onChange("scaffold-tree")}
      >
        <GitFork className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">Scaffold</span>
      </Button>
      <Button
        type="button"
        variant={mode === "clusters" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2 gap-1.5"
        aria-label="Cluster view"
        aria-pressed={mode === "clusters"}
        disabled={isDisabled("clusters")}
        title={isDisabled("clusters") ? "Need at least 10 molecules for cluster map" : undefined}
        onClick={() => mode !== "clusters" && onChange("clusters")}
      >
        <ChartScatter className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">Cluster</span>
      </Button>
    </div>
  );
}
