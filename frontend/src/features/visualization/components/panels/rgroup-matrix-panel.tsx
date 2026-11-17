"use client";

import {
  type MatrixGridCell,
  PotencyRamp,
  RGroupMatrixGrid,
  cellKey,
} from "@/features/sar-analysis/components/rgroup-matrix-grid";
import { potencyShade } from "@/features/sar-analysis/lib/sar-activity-display";
import { fragmentDisplay } from "@/features/sar-analysis/lib/sar-fragment-label";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { useMemo } from "react";
import { usePassMask } from "../../hooks/use-pass-mask";
import { column } from "../../lib/dataset";
import { fieldLabel, panelNote } from "../../lib/traces/common";
import { buildRGroupMatrix, selectedCells } from "../../lib/traces/rgroup-matrix";
import { useWorkbench } from "../../store/workbench-context";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";

/** Lower-is-better potencies: a DR fit (Runs) or its geomean (Batches, Compounds). */
const POTENCY = new Set(["fit", "geomean"]);

const rows = (n: number, one: string, many: string) =>
  `${n.toLocaleString()} ${n === 1 ? `row ${one}` : `rows ${many}`}`;

/** Rows × columns of two R positions of one R-groups set over the passing rows: each cell
 * the median (or mean) of the chosen value, or its compound count, shaded by potency when
 * the value is one. Clicking a cell selects its rows. */
export function RGroupMatrixPanel({ panel, ds }: { panel: PanelConfig; ds: Dataset }) {
  const mask = usePassMask(ds);
  const selection = useWorkbench((s) => s.selection);
  const setSelection = useWorkbench((s) => s.setSelection);
  const m = useMemo(() => buildRGroupMatrix(ds, panel, mask), [ds, panel, mask]);
  const selected = useMemo(() => selectedCells(m, ds, selection), [m, ds, selection]);

  const label = (key?: string) => (key ? fieldLabel(ds, key) : "—");
  const [yLabel, xLabel] = [label(panel.category), label(panel.x)];
  const value = panel.y ? column(ds, panel.y) : undefined;
  const potency = POTENCY.has(value?.provenance.aggregation ?? "");
  const unit = value?.unit ? ` ${value.unit}` : "";

  const cells = useMemo(() => {
    const shown = m.yValues.flatMap((y) => m.xValues.map((x) => [y, x] as const));
    const values = [...m.cells.values()].map((c) => c.value).filter((v) => v !== null);
    const reference = values.length ? Math.min(...values) : null;
    const out = new Map<string, MatrixGridCell>();
    for (const [y, x] of shown) {
      const key = cellKey(y, x);
      const c = m.cells.get(key);
      if (!c) continue;
      const n = `${c.compounds.toLocaleString()} ${c.compounds === 1 ? "compound" : "compounds"}`;
      out.set(key, {
        text: !value
          ? c.compounds.toLocaleString()
          : c.value === null
            ? "—"
            : `${formatMeasurementValue(c.value, 4)}${unit}`,
        badge: value ? `n=${c.compounds}` : undefined,
        shade: potency ? potencyShade(c.value, reference) : "",
        title: `${yLabel} ${fragmentDisplay(y).label} × ${xLabel} ${fragmentDisplay(x).label}: ${n}`,
        selected: selected.has(key),
      });
    }
    return out;
  }, [m, selected, value, potency, unit, yLabel, xLabel]);

  const unmatched = m.skipped - m.noCompound;
  const notes = [
    unmatched > 0 && rows(unmatched, "doesn't match the core", "don't match the core"),
    m.noCompound > 0 && rows(m.noCompound, "has no compound", "have no compound"),
    panelNote(null, m.censored),
    m.truncated &&
      `Showing top ${m.yValues.length} of ${m.yTotal} ${yLabel} × top ${m.xValues.length} of ${m.xTotal} ${xLabel} (most-populated).`,
  ].filter(Boolean);

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {m.yValues.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No passing row has both {yLabel} and {xLabel}.
          </p>
        ) : (
          <RGroupMatrixGrid
            yLabel={yLabel}
            xLabel={xLabel}
            yValues={m.yValues}
            xValues={m.xValues}
            cells={cells}
            onCellClick={(y, x) => {
              const c = m.cells.get(cellKey(y, x));
              if (c) setSelection(c.rows.map((i) => ds.row_ids[i]));
            }}
          />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 px-2 pb-1 text-xs text-muted-foreground">
        {value &&
          (potency ? (
            <>
              <span className="font-medium text-foreground">{value.label}</span>
              <PotencyRamp />
            </>
          ) : (
            <span>Shading is for potencies only</span>
          ))}
        {notes.map((note) => (
          <span key={String(note)}>{note}</span>
        ))}
      </div>
    </div>
  );
}
