"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { BookmarkPlus, Columns2, Layers, ListPlus, Rows2, Rows3, Settings2 } from "lucide-react";
import { useReportConfig } from "../../hooks/use-report-config";
import { useAggregationMode } from "../../lib/use-aggregation-mode";
import type { PlotLayout, SearchDisplayPreset } from "../../types";
import { AggregationControl } from "./aggregation-control";

export function ResultsToolbarLeft({
  resultCount,
  selectedCount,
}: {
  resultCount: number | null;
  selectedCount: number;
}) {
  return (
    <>
      <h2 className="text-base font-semibold tracking-tight">
        {resultCount?.toLocaleString() ?? "–"}{" "}
        <span className="font-normal text-muted-foreground">compounds</span>
      </h2>
      {selectedCount > 0 && (
        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          {selectedCount} selected
        </span>
      )}
    </>
  );
}

export function ResultsToolbarActions({
  onSaveSearch,
  busy,
}: {
  onSaveSearch: () => void;
  busy?: boolean;
}) {
  return (
    <Button variant="ghost" size="sm" disabled={busy} onClick={onSaveSearch}>
      <BookmarkPlus /> Save search
    </Button>
  );
}

export function ResultsViewControls({
  onCustomizeReport,
  scopeForcesSingleRun,
  busy,
  hasAssays,
  canOverlay,
}: {
  onCustomizeReport: () => void;
  scopeForcesSingleRun?: boolean;
  busy?: boolean;
  hasAssays: boolean;
  /** A split protocol has curves: offer drawing its groups overlaid. */
  canOverlay?: boolean;
}) {
  const { mode, setMode } = useAggregationMode();
  const { config, updateConfig } = useReportConfig();
  return (
    <>
      <fieldset
        aria-label="Results display"
        className="inline-flex shrink-0 rounded-lg bg-muted/70 p-1"
      >
        {(["compact", "detailed"] as SearchDisplayPreset[]).map((preset) => {
          const active = (config.displayPreset ?? "detailed") === preset;
          const Icon = preset === "compact" ? Rows3 : Rows2;
          return (
            <Button
              key={preset}
              size="sm"
              variant="ghost"
              className={cn(
                "h-7 gap-1.5 px-2 text-xs font-medium text-foreground/70",
                active && "bg-background text-foreground shadow-sm hover:bg-background",
              )}
              aria-pressed={active}
              title={
                preset === "compact"
                  ? "Dense rows: small structures, values only"
                  : "Larger structures, curve plots and run dates"
              }
              onClick={() =>
                updateConfig({
                  displayPreset: preset,
                  imageSize: preset === "compact" ? "small" : "medium",
                })
              }
            >
              <Icon className="size-3.5" />
              {preset === "compact" ? "Compact" : "Detailed"}
            </Button>
          );
        })}
      </fieldset>
      {canOverlay && (config.displayPreset ?? "detailed") === "detailed" && (
        <fieldset
          aria-label="Plot layout"
          className="inline-flex shrink-0 rounded-lg bg-muted/70 p-1"
        >
          {(["side_by_side", "overlay"] as PlotLayout[]).map((layout) => {
            const active = (config.plotLayout ?? "side_by_side") === layout;
            const Icon = layout === "overlay" ? Layers : Columns2;
            return (
              <Button
                key={layout}
                size="sm"
                variant="ghost"
                className={cn(
                  "h-7 gap-1.5 px-2 text-xs font-medium text-foreground/70",
                  active && "bg-background text-foreground shadow-sm hover:bg-background",
                )}
                aria-pressed={active}
                title={
                  layout === "overlay"
                    ? "Every group's curve in one plot, coloured like its column header"
                    : "One plot per group"
                }
                onClick={() => updateConfig({ plotLayout: layout })}
              >
                <Icon className="size-3.5" />
                {layout === "overlay" ? "Overlay" : "Separate"}
              </Button>
            );
          })}
        </fieldset>
      )}
      {hasAssays && (
        <AggregationControl
          mode={mode}
          onChange={setMode}
          disabled={scopeForcesSingleRun}
          busy={busy}
        />
      )}
      <Button
        variant="ghost"
        size="sm"
        className="text-xs font-medium"
        disabled={busy}
        onClick={onCustomizeReport}
      >
        <Settings2 className="size-3.5" /> Columns & display
      </Button>
    </>
  );
}

export function ResultsSelectionActions({
  selectedCount,
  onCompare,
  onAddToCollection,
  onClearSelection,
  busy,
}: {
  selectedCount: number;
  onCompare: () => void;
  onAddToCollection: () => void;
  onClearSelection: () => void;
  busy?: boolean;
}) {
  if (selectedCount === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Select compounds to compare or add to a collection
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-primary/5 px-3 py-2">
      <span className="mr-1 text-xs font-medium text-primary">{selectedCount} selected</span>
      <Button
        variant="default"
        size="sm"
        disabled={busy || selectedCount < 2 || selectedCount > 4}
        onClick={onCompare}
        title="Select 2–4 compounds using the row checkboxes"
      >
        <Columns2 /> Compare ({selectedCount})
      </Button>
      <Button variant="outline" size="sm" disabled={busy} onClick={onAddToCollection}>
        <ListPlus /> Add to collection
      </Button>
      {(selectedCount < 2 || selectedCount > 4) && (
        <span className="text-xs text-muted-foreground">
          {selectedCount < 2 ? "Select one more to compare" : "Select up to 4 to compare"}
        </span>
      )}
      <Button variant="ghost" size="sm" className="ml-auto text-xs" onClick={onClearSelection}>
        Clear selection
      </Button>
    </div>
  );
}
