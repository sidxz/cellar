"use client";

/**
 * 2-axis R-group heatmap — server-aggregated. Pick two R-positions → POST
 * /heatmap → a grid of (Ry × Rx) cells, each with the most-potent (argmin)
 * representative + count + a curve snapshot. Coloring uses `potencyShade`
 * (sar-analysis/lib/sar-activity-display) anchored on the server-supplied
 * `activity_reference` — the min over the whole (uncapped) scored set, the same
 * anchor the R-group table uses, so the two surfaces shade identically even when
 * an axis is truncated. Gated to `dr_curve`. A matched cell with no value for the
 * channel renders uncolored (a tested-but-unscreened corner). Click a cell →
 * expand its representative's DR curve off the server `best_snapshot`. Axes that
 * exceed the server top-30 cap surface an honest "top 30 of N" note.
 */

import { activityValueToCurveSnapshot } from "@/features/research-organization/lib/activity-curve-snapshot";
import {
  CurveExpandDialog,
  type ExpandedCurve,
} from "@/features/screen-campaign/components/grid/curve-expand-dialog";
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { HeatmapCellView } from "@/shared/lib/api/model";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { useEffect, useMemo, useState } from "react";
import { useHeatmapAggregation } from "../hooks/use-heatmap-aggregation";
import { potencyShade } from "../lib/sar-activity-display";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { type MatrixGridCell, PotencyRamp, RGroupMatrixGrid, cellKey } from "./rgroup-matrix-grid";

export { cellKey };

export interface RGroupHeatmapProps {
  runId: string;
  projectionId: string;
  labels: string[];
  colorSpec: SarColorSpec;
}

export function RGroupHeatmap({ runId, projectionId, labels, colorSpec }: RGroupHeatmapProps) {
  const [axisY, setAxisY] = useState<string>(() => labels[0] ?? "");
  const [axisX, setAxisX] = useState<string>(() => labels[1] ?? "");
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);

  // Re-sync the axes whenever the run's label set changes (e.g. switching to a
  // previously cached core that resolves without an unmount) so we never query a
  // stale axis the new core doesn't have. Functional updates read the current
  // axis without needing it in the deps; keyed on the label set.
  const labelsKey = labels.join("");
  // biome-ignore lint/correctness/useExhaustiveDependencies: labelsKey encodes labels
  useEffect(() => {
    setAxisY((cur) => (labels.includes(cur) ? cur : (labels[0] ?? "")));
    setAxisX((cur) => (labels.includes(cur) ? cur : (labels[1] ?? labels[0] ?? "")));
  }, [labelsKey]);

  const { data, isLoading } = useHeatmapAggregation({ runId, projectionId, axisY, axisX });

  const shadeByPotency = colorSpec.source === "dr_curve";
  // Shared anchor with the R-group table: the server's full-set min, not a
  // client recompute over the (truncation-capped) returned cells.
  const reference = data?.activity_reference ?? null;
  const cellsByKey = useMemo(() => {
    const m = new Map<string, HeatmapCellView>();
    for (const c of data?.cells ?? []) m.set(cellKey(c.y, c.x), c);
    return m;
  }, [data]);
  const gridCells = useMemo(() => {
    const m = new Map<string, MatrixGridCell>();
    for (const [key, cell] of cellsByKey) {
      const unit = (cell.best_snapshot as { unit?: string | null })?.unit
        ? ` ${(cell.best_snapshot as { unit?: string | null }).unit}`
        : "";
      const extra = cell.count - 1;
      m.set(key, {
        text: cell.best_scalar != null ? `${formatMeasurementValue(cell.best_scalar)}${unit}` : "—",
        badge: extra > 0 ? `+${extra}` : undefined,
        shade: shadeByPotency ? potencyShade(cell.best_scalar ?? null, reference) : "",
        title: `${cell.count} compound(s)`,
      });
    }
    return m;
  }, [cellsByKey, shadeByPotency, reference]);

  if (labels.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Need at least two R-group positions for a heatmap.
      </p>
    );
  }
  if (isLoading || !data) {
    return <p className="text-xs text-muted-foreground">Computing heatmap…</p>;
  }

  function handleCellClick(cell: HeatmapCellView) {
    const snapshot: CurveSnapshot | null = activityValueToCurveSnapshot(
      cell.best_snapshot as never,
      {
        value: cell.best_scalar,
        label: colorSpec.label,
      },
    );
    if (!snapshot) return;
    setOpenCurve({
      ...snapshot,
      unit: (cell.best_snapshot as { unit?: string | null })?.unit ?? null,
      moleculeLabel: cell.best_molecule_label,
      channelLabel: colorSpec.label,
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">Rows (Y):</span>
        <Select value={axisY} onValueChange={setAxisY}>
          <SelectTrigger className="h-7 w-28 text-xs" aria-label="Y axis position">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {labels.map((l) => (
              <SelectItem key={l} value={l} className="text-xs">
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground">Columns (X):</span>
        <Select value={axisX} onValueChange={setAxisX}>
          <SelectTrigger className="h-7 w-28 text-xs" aria-label="X axis position">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {labels.map((l) => (
              <SelectItem key={l} value={l} className="text-xs">
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {axisY === axisX && (
          <span className="text-amber-700 dark:text-amber-300">
            Same position on both axes — diagonal only.
          </span>
        )}
        {data.truncated && (
          <span className="text-amber-700 dark:text-amber-300">
            Showing top {data.y_values.length} of {data.y_total} {axisY} × top{" "}
            {data.x_values.length} of {data.x_total} {axisX} (most-populated).
          </span>
        )}
      </div>

      <RGroupMatrixGrid
        yLabel={axisY}
        xLabel={axisX}
        yValues={data.y_values}
        xValues={data.x_values}
        cells={gridCells}
        onCellClick={(y, x) => {
          const cell = cellsByKey.get(cellKey(y, x));
          if (cell) handleCellClick(cell);
        }}
      />

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground">{colorSpec.label}</span>
        {shadeByPotency ? (
          <PotencyRamp />
        ) : (
          <span>higher-is-better readout — cells show the best value (uncolored).</span>
        )}
      </div>

      <CurveExpandDialog data={openCurve} onOpenChange={(open) => !open && setOpenCurve(null)} />
    </div>
  );
}
