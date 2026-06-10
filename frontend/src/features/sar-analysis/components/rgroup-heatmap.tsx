"use client";

/**
 * 2-axis R-group heatmap for the SAR workbench.
 *
 * Pick two R-positions → a colored grid of (Ry × Rx) cells. Each cell holds the
 * molecules carrying that substituent combination plus their best (most-potent)
 * activity scalar. The grid is sparse: combos with no molecule render as a
 * hatched "gap" ("make?") so the chemist can read both the SAR signal and the
 * unexplored corners of the matrix at a glance.
 *
 * Coloring reuses the table's exact potency machinery — `pickReference` anchors
 * the green→red ramp to the most-potent cell and `potencyShade` buckets each
 * cell by fold-off. Both assume LOWER-is-better, so coloring is gated to
 * `colorSpec.source === "dr_curve"`; `readout_data` cells render uncolored (the
 * same gating the table applies) to avoid painting the best compounds red.
 *
 * Clicking a populated cell expands its most-potent molecule's DR curve via the
 * shared {@link CurveExpandDialog}, mirroring the table's row-click so the SAR
 * expand draws the same picture as the campaign / run / search surfaces.
 */

import type { Molecule } from "@/features/chemical-registration/types";
import type { ActivityValue } from "@/features/research-organization/types";
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
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useMemo, useState } from "react";
import { buildHeatmapGrid, heatmapCellKey } from "../lib/rgroup-heatmap-grid";
import { type SarColorSpec, colorSpecScalar } from "../lib/sar-color-spec";
// Reuse the table's exact potency reference + shading + snapshot mapping so the
// heatmap and the table read identically. (Importing from the sibling component
// is acceptable for now — see B4 spec.)
import { pickReference, potencyShade, snapshotFromActivity } from "./rgroup-table";

export interface RGroupHeatmapProps {
  decomposition: RGroupDecompositionResponse;
  /** Activity cell per molecule id (from `useSarActivity`), keyed by the same
   *  `molecule_id` the assignments are keyed by. */
  activityByMolecule: Record<string, ActivityValue | undefined>;
  /** Names the (protocol, readout/intercept) pair the heatmap colors by. Null
   *  ⇒ empty state (no activity picked yet). */
  colorSpec: SarColorSpec | null;
  /** Loaded molecules — used for cell-click labels (reg number / name). */
  molecules: Molecule[];
}

/** Hatched "gap" background for combos no molecule occupies — reads as an
 *  unexplored / "make?" corner of the matrix. */
const GAP_CLASS =
  "bg-[repeating-linear-gradient(45deg,transparent,transparent_5px,var(--color-muted)_5px,var(--color-muted)_7px)]";

function moleculeLabelFor(m: Molecule | undefined, fallbackId: string): string {
  return m?.registration_number ?? m?.name ?? fallbackId;
}

export function RGroupHeatmap({
  decomposition,
  activityByMolecule,
  colorSpec,
  molecules,
}: RGroupHeatmapProps) {
  const labels = decomposition.rgroup_labels;

  // Default the two axes to the first two R-positions. State is keyed by label
  // string so it survives a decomposition change with the same labels.
  const [axisY, setAxisY] = useState<string>(() => labels[0] ?? "");
  const [axisX, setAxisX] = useState<string>(() => labels[1] ?? "");

  // Clicked-open curve (most-potent molecule of the clicked cell). Null cells
  // and readout_data cells (no fittable DR snapshot) leave it null = no-op.
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);

  const moleculeById = useMemo(() => new Map(molecules.map((m) => [m.id, m])), [molecules]);

  // Coloring is only meaningful for lower-is-better DR potencies (same gating
  // as the table). For readout_data the cell value still renders, uncolored.
  const shadeByPotency = colorSpec?.source === "dr_curve";

  // Build the grid + the potency reference. `scalarOf` extracts the single
  // scalar the active spec names from each molecule's activity cell.
  const { grid, reference } = useMemo(() => {
    if (!colorSpec) {
      return { grid: null as ReturnType<typeof buildHeatmapGrid> | null, reference: null };
    }
    const scalarOf = (molId: string) => colorSpecScalar(activityByMolecule[molId], colorSpec);
    const g = buildHeatmapGrid(decomposition.assignments, axisY, axisX, scalarOf);
    const ref = pickReference(Object.values(g.cells).map((c) => c.bestScalar));
    return { grid: g, reference: ref };
  }, [colorSpec, activityByMolecule, decomposition.assignments, axisY, axisX]);

  // ─── Empty states ───────────────────────────────────────────────────────
  if (!colorSpec) {
    return (
      <p className="text-xs text-muted-foreground">
        Pick an activity (Color by) to populate the heatmap.
      </p>
    );
  }
  if (labels.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Need at least two R-group positions for a heatmap.
      </p>
    );
  }

  // grid is non-null here (colorSpec is set), but narrow for TS.
  if (!grid) return null;

  function handleCellClick(bestMolId: string) {
    const av = activityByMolecule[bestMolId];
    const snapshot: CurveSnapshot | null = snapshotFromActivity(av);
    if (!snapshot || !colorSpec) return; // readout_data / no-curve cells: no-op
    setOpenCurve({
      ...snapshot,
      unit: av?.unit ?? null,
      moleculeLabel: moleculeLabelFor(moleculeById.get(bestMolId), bestMolId),
      channelLabel: colorSpec.label,
    });
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Axis pickers */}
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
      </div>

      {/* Grid */}
      <div className="overflow-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              {/* Corner: shows which positions the axes map to. */}
              <th className="sticky left-0 z-10 bg-background p-1 text-left align-bottom font-medium text-muted-foreground">
                {axisY} ↓ / {axisX} →
              </th>
              {grid.xValues.map((x) => (
                <th key={x} className="p-1 align-bottom font-normal" scope="col">
                  <div className="flex w-20 flex-col items-center gap-0.5">
                    <StructureThumbnail smiles={x} size={32} />
                    <span className="break-all font-mono text-[9px] leading-tight text-muted-foreground">
                      {x}
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.yValues.map((y) => (
              <tr key={y}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-background p-1 text-left align-middle font-normal"
                >
                  <div className="flex w-24 items-center gap-1">
                    <StructureThumbnail smiles={y} size={32} className="shrink-0" />
                    <span className="break-all font-mono text-[9px] leading-tight text-muted-foreground">
                      {y}
                    </span>
                  </div>
                </th>
                {grid.xValues.map((x) => {
                  const cell = grid.cells[heatmapCellKey(y, x)];
                  if (!cell) {
                    // Gap — no molecule with this combo. A "make?" candidate.
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
                  const shade = shadeByPotency ? potencyShade(cell.bestScalar, reference) : "";
                  // Expand the most-potent molecule of the cell on click; read
                  // its unit so the displayed value is consistent with the id
                  // used for curve-expand.
                  const bestMolId = bestMoleculeId(cell.moleculeIds, activityByMolecule, colorSpec);
                  const unit = activityByMolecule[bestMolId]?.unit
                    ? ` ${activityByMolecule[bestMolId]?.unit}`
                    : "";
                  const extra = cell.moleculeIds.length - 1;
                  return (
                    <td key={x} className="p-0">
                      {/* Button = native click + keyboard target (a11y), filling
                          the cell. The potency shade rides on the button. */}
                      <button
                        type="button"
                        className={cn(
                          "flex h-16 w-20 cursor-pointer flex-col items-center justify-center gap-0.5 rounded border border-border text-center",
                          shade || "bg-muted/30",
                        )}
                        onClick={() => handleCellClick(bestMolId)}
                        title={`${cell.moleculeIds.length} compound(s)`}
                      >
                        <span className="font-medium tabular-nums">
                          {cell.bestScalar != null
                            ? `${formatMeasurementValue(cell.bestScalar)}${unit}`
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

      {/* Legend */}
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

      <CurveExpandDialog
        data={openCurve}
        onOpenChange={(open) => {
          if (!open) setOpenCurve(null);
        }}
      />
    </div>
  );
}

/**
 * The most-potent molecule id within a cell = the one whose scalar equals the
 * cell's min. Falls back to the first id when none of them carry a scalar (the
 * click still opens, and `snapshotFromActivity` no-ops if there's no curve).
 */
function bestMoleculeId(
  moleculeIds: string[],
  activityByMolecule: Record<string, ActivityValue | undefined>,
  colorSpec: SarColorSpec,
): string {
  let bestId = moleculeIds[0];
  let bestScalar: number | null = null;
  for (const id of moleculeIds) {
    const s = colorSpecScalar(activityByMolecule[id], colorSpec);
    if (s == null || !Number.isFinite(s)) continue;
    if (bestScalar == null || s < bestScalar) {
      bestScalar = s;
      bestId = id;
    }
  }
  return bestId;
}
