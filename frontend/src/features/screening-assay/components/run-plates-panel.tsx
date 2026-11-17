"use client";

import type { PlateColorBy } from "../lib/plate-map-values";
import type { Run } from "../types";
import { RunHeatmapPanel } from "./run-heatmap-panel";

export function RunPlatesPanel({
  run,
  view,
  onViewChange,
  onOpenResults,
}: {
  run: Run;
  view: PlateColorBy;
  onViewChange: (view: PlateColorBy) => void;
  onOpenResults: () => void;
}) {
  return (
    <RunHeatmapPanel
      run={run}
      colorBy={view}
      onColorByChange={onViewChange}
      onOpenResults={onOpenResults}
    />
  );
}
