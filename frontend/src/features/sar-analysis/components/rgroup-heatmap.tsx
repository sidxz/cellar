"use client";

/**
 * 2-axis R-group heatmap — server-aggregated. Pick two R-positions → POST
 * /heatmap → a grid of (Ry × Rx) cells, each with the most-potent (argmin)
 * representative + count + a curve snapshot. Coloring reuses the table's
 * `pickReference`/`potencyShade` over the (small) returned cells, gated to
 * `dr_curve`. Click a cell → expand its representative's DR curve off the
 * server `best_snapshot`. Axes that exceed the server top-30 cap surface an
 * honest "top 30 of N" note.
 */

import {
  CurveExpandDialog,
  type ExpandedCurve,
} from "@/features/screen-campaign/components/grid/curve-expand-dialog";
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { StructureThumbnail } from "@/shared/components/chemistry";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { HeatmapCellView } from "@/shared/lib/api/model";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useMemo, useState } from "react";
import { useHeatmapAggregation } from "../hooks/use-heatmap-aggregation";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { fragmentDisplay } from "../lib/sar-fragment-label";
import { pickReference, potencyShade, snapshotFromActivity } from "./rgroup-table";

export interface RGroupHeatmapProps {
  runId: string;
  projectionId: string;
  labels: string[];
  colorSpec: SarColorSpec;
}

const GAP_CLASS =
  "bg-[repeating-linear-gradient(45deg,transparent,transparent_5px,var(--color-muted)_5px,var(--color-muted)_7px)]";

/** Stable, collision-free key for a (y, x) cell. */
export function cellKey(y: string, x: string): string {
  return JSON.stringify([y, x]);
}

/** Most-potent (min) best_scalar across the returned cells — the ramp anchor. */
export function heatmapReference(cells: Pick<HeatmapCellView, "best_scalar">[]): number | null {
  return pickReference(cells.map((c) => c.best_scalar));
}

function AxisFragment({ smiles, orientation }: { smiles: string; orientation: "col" | "row" }) {
  const frag = fragmentDisplay(smiles);
  return (
    <div
      className={cn(
        orientation === "col"
          ? "flex w-20 flex-col items-center gap-0.5"
          : "flex w-24 items-center gap-1",
      )}
      title={frag.title}
    >
      {frag.thumbnailSmiles && (
        <StructureThumbnail
          smiles={frag.thumbnailSmiles}
          size={32}
          className={orientation === "row" ? "shrink-0" : undefined}
        />
      )}
      <span className="break-all text-[9px] leading-tight text-muted-foreground">{frag.label}</span>
    </div>
  );
}

export function RGroupHeatmap({ runId, projectionId, labels, colorSpec }: RGroupHeatmapProps) {
  const [axisY, setAxisY] = useState<string>(() => labels[0] ?? "");
  const [axisX, setAxisX] = useState<string>(() => labels[1] ?? "");
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);

  const { data, isLoading } = useHeatmapAggregation({ runId, projectionId, axisY, axisX });

  const shadeByPotency = colorSpec.source === "dr_curve";
  const reference = useMemo(() => (data ? heatmapReference(data.cells) : null), [data]);
  const cellsByKey = useMemo(() => {
    const m = new Map<string, HeatmapCellView>();
    for (const c of data?.cells ?? []) m.set(cellKey(c.y, c.x), c);
    return m;
  }, [data]);

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
    const snapshot: CurveSnapshot | null = snapshotFromActivity(cell.best_snapshot as never);
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

      <div className="overflow-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-background p-1 text-left align-bottom font-medium text-muted-foreground">
                {axisY} ↓ / {axisX} →
              </th>
              {data.x_values.map((x) => (
                <th key={x} className="p-1 align-bottom font-normal" scope="col">
                  <AxisFragment smiles={x} orientation="col" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.y_values.map((y) => (
              <tr key={y}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-background p-1 text-left align-middle font-normal"
                >
                  <AxisFragment smiles={y} orientation="row" />
                </th>
                {data.x_values.map((x) => {
                  const cell = cellsByKey.get(cellKey(y, x));
                  if (!cell) {
                    return (
                      <td
                        key={x}
                        className={cn(
                          "h-16 w-20 rounded border border-dashed border-muted-foreground/30 text-center align-middle text-muted-foreground/50",
                          GAP_CLASS,
                        )}
                        title="No compound with this combination — make?"
                      >
                        <span className="text-[10px]">make?</span>
                      </td>
                    );
                  }
                  const shade = shadeByPotency ? potencyShade(cell.best_scalar, reference) : "";
                  const unit = (cell.best_snapshot as { unit?: string | null })?.unit
                    ? ` ${(cell.best_snapshot as { unit?: string | null }).unit}`
                    : "";
                  const extra = cell.count - 1;
                  return (
                    <td key={x} className="p-0">
                      <button
                        type="button"
                        className={cn(
                          "flex h-16 w-20 cursor-pointer flex-col items-center justify-center gap-0.5 rounded border border-border text-center",
                          shade || "bg-muted/30",
                        )}
                        onClick={() => handleCellClick(cell)}
                        title={`${cell.count} compound(s)`}
                      >
                        <span className="font-medium tabular-nums">
                          {cell.best_scalar != null
                            ? `${formatMeasurementValue(cell.best_scalar)}${unit}`
                            : "—"}
                        </span>
                        {extra > 0 && (
                          <span className="rounded-full bg-foreground/10 px-1.5 text-[10px] text-muted-foreground">
                            +{extra}
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground">{colorSpec.label}</span>
        {shadeByPotency ? (
          <>
            <span>potent</span>
            <span className="h-3 w-5 rounded bg-green-600/30" />
            <span className="h-3 w-5 rounded bg-green-500/20" />
            <span className="h-3 w-5 rounded bg-amber-500/20" />
            <span className="h-3 w-5 rounded bg-orange-500/25" />
            <span className="h-3 w-5 rounded bg-red-600/30" />
            <span>weak</span>
          </>
        ) : (
          <span>higher-is-better readout — cells show the best value (uncolored).</span>
        )}
      </div>

      <CurveExpandDialog data={openCurve} onOpenChange={(open) => !open && setOpenCurve(null)} />
    </div>
  );
}
