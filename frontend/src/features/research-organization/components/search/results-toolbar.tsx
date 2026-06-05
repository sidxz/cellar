"use client";

/**
 * Two sibling render-only fragments composing the search-page toolbar:
 *
 *   - {@link ResultsToolbarLeft}: result count + select-all/none status line.
 *   - {@link ResultsToolbarActions}: action buttons (Add to Collection /
 *     Customize Report / Save Search).
 *
 * Both are slotted into the underlying DataGrid's toolbar via its
 * `toolbarLeft` and `toolbarActions` props so they share the same row as
 * the Export dropdown — no separate page-level toolbar row, no extra
 * vertical space for Export.
 */

import { Button } from "@/shared/components/ui/button";
import { BookmarkPlus, ListPlus, Settings2 } from "lucide-react";
import { useAggregationMode } from "../../lib/use-aggregation-mode";
import { AggregationControl } from "./aggregation-control";

interface ResultsToolbarLeftProps {
  resultCount: number | null;
  selectedCount: number;
  onSelectAll: () => void;
  onSelectNone: () => void;
}

export function ResultsToolbarLeft({
  resultCount,
  selectedCount,
  onSelectAll,
  onSelectNone,
}: ResultsToolbarLeftProps) {
  return (
    <>
      <span className="text-sm text-muted-foreground">
        <strong className="text-foreground">{resultCount?.toLocaleString() ?? "–"}</strong> results
      </span>
      {selectedCount > 0 && (
        <span className="text-sm text-primary font-medium">· {selectedCount} selected</span>
      )}
      <span className="text-sm text-muted-foreground/60">
        Select:{" "}
        <button type="button" onClick={onSelectAll} className="text-primary hover:text-primary/80">
          all
        </button>
        {" / "}
        <button type="button" onClick={onSelectNone} className="text-primary hover:text-primary/80">
          none
        </button>
      </span>
    </>
  );
}

interface ResultsToolbarActionsProps {
  selectedCount: number;
  onAddToCollection: () => void;
  onCustomizeReport: () => void;
  onSaveSearch: () => void;
  /**
   * True when the active query has narrowed every activity criterion to one
   * run, so the aggregation dropdown is a no-op on every cell. The page
   * computes this from `currentQuery.criteria` via `computeScopeForcesSingleRun`
   * and forwards it down so the toolbar can swap the dropdown for a muted
   * static label.
   */
  scopeForcesSingleRun?: boolean;
}

export function ResultsToolbarActions({
  selectedCount,
  onAddToCollection,
  onCustomizeReport,
  onSaveSearch,
  scopeForcesSingleRun,
}: ResultsToolbarActionsProps) {
  // URL-synced aggregation mode lives in the toolbar — the page reads the
  // same hook independently for the search body, so we don't have to
  // plumb mode/setMode through props. The hook is a thin URL-state
  // wrapper (no remote calls), so duplicate subscriptions are cheap.
  const { mode: aggregationMode, setMode: setAggregationMode } = useAggregationMode();
  return (
    <>
      <AggregationControl
        mode={aggregationMode}
        onChange={setAggregationMode}
        disabled={scopeForcesSingleRun}
      />
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-sm gap-1.5"
        disabled={selectedCount === 0}
        onClick={onAddToCollection}
      >
        <ListPlus className="h-3.5 w-3.5" />
        Add to Collection
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-sm gap-1.5"
        onClick={onCustomizeReport}
      >
        <Settings2 className="h-3.5 w-3.5" />
        Customize Report
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-sm gap-1.5 border-primary/20 bg-primary/10 text-primary hover:bg-primary/20"
        onClick={onSaveSearch}
      >
        <BookmarkPlus className="h-3.5 w-3.5" />
        Save Search
      </Button>
    </>
  );
}
