"use client";

import {
  DoseResponseFigure,
  type FigureSize,
} from "@/features/screening-assay/components/dose-response-figure";
import {
  type CurveFrame,
  curveFrame,
  drawnPoints,
} from "@/features/screening-assay/lib/curve-frame";
import { isPercentNormalization } from "@/features/screening-assay/lib/dose-response-math";
import { createContext, memo, useContext, useMemo } from "react";
import { activityValueToCurveSnapshot } from "../../lib/activity-curve-snapshot";
import type { ActivityValue } from "../../types";

/** The search grid's curve frames: a cell asks by its activity key and whether its curve
 *  fits a % layer. Absent (outside the grid): each cell frames itself. */
export const CurveFramesContext = createContext<
  ((key: string, percent: boolean) => CurveFrame) | null
>(null);

/** One frame per curve column over every loaded result, worked out once per column.
 *  With "List all runs" each run's own curve is drawn, so its points count too. */
export function useCurveFramesFor(
  rows: readonly { activity?: Record<string, ActivityValue> | null }[],
) {
  return useMemo(() => {
    const cache = new Map<string, CurveFrame>();
    return (key: string, percent: boolean) => {
      const id = `${key}\u0000${percent}`;
      let frame = cache.get(id);
      if (!frame) {
        frame = curveFrame(
          rows.flatMap((r) => {
            const av = r.activity?.[key];
            return [
              ...drawnPoints(av),
              ...(av?.runs ?? []).flatMap((run) => drawnPoints(run.curve_snapshot)),
            ];
          }),
          { percent },
        );
        cache.set(id, frame);
      }
      return frame;
    };
  }, [rows]);
}

/** "List all runs": each listed run's curve, labelled by its date. Entry i takes
 *  `overlayColor(i)`, the colour of the i-th dot in the value list (a run without
 *  a fit keeps its slot). Null when no run carries a curve. */
export function runOverlayCurves(value: ActivityValue | undefined) {
  const runs = value?.runs ?? [];
  if (!runs.some((r) => r.curve_snapshot)) return null;
  return runs.map((r) => ({ curve: r.curve_snapshot, label: r.run_date }));
}

interface DoseResponseCellProps {
  value?: ActivityValue;
  /** The cell's activity key, so it shares its column's frame. */
  frameKey?: string;
  /** The curve fits a % layer, so its frame keeps the 0 % and 100 % anchors. */
  percent?: boolean;
  /** "List all runs": draw every listed run's curve, coloured like its dot. */
  listRuns?: boolean;
}

/**
 * Search results IC50 plot cell. Hands the (params + raw_data) tuple to
 * the shared <DoseResponseFigure /> so the search drawing matches the
 * protocol Activity tab + the campaign grid 1:1 — same component, same
 * trace builder, same color tokens, same axis-range strategy.
 */
function DoseResponseCellInner({
  value,
  frameKey,
  percent = false,
  listRuns = false,
}: DoseResponseCellProps) {
  const frameFor = useContext(CurveFramesContext);
  // The layer the cell's curve names wins over the column's guess from the protocol.
  const isPercent =
    value?.fitted_layer === undefined ? percent : isPercentNormalization(value.fitted_layer);
  const frame = frameKey && frameFor ? frameFor(frameKey, isPercent) : undefined;
  const runCurves = listRuns ? runOverlayCurves(value) : null;
  if (runCurves) {
    return (
      <DoseResponseFigure
        curves={runCurves}
        size="cell"
        unit={value?.unit ?? null}
        xRange={frame?.xRange}
        yRange={frame?.yRange}
      />
    );
  }
  const curve = activityValueToCurveSnapshot(value);
  // `curve` non-null implies `value` non-null (the mapper guards `!av`); the
  // `!value` keeps that provable for the type checker without a `!` assertion.
  if (!curve || !value) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }
  return (
    <DoseResponseFigure
      curve={curve}
      size="cell"
      unit={value.unit ?? null}
      xRange={frame?.xRange}
      yRange={frame?.yRange}
    />
  );
}

export const DoseResponseCell = memo(DoseResponseCellInner);

interface DoseResponseOverlayProps {
  /** One entry per split group, in header order; `value` absent when the
   *  compound has no cell in that group. */
  entries: { value?: ActivityValue; label: string }[];
  /** "cell" in the grid; "full" (legend, hover) in the drawer. */
  size?: FigureSize;
}

/** Every split group's curve in one plot. Entry `i` takes `overlayColor(i)`,
 *  the colour on its group's header, so a missing cell keeps its slot. */
export function DoseResponseOverlay({ entries, size = "cell" }: DoseResponseOverlayProps) {
  const curves = entries.map((e) => ({
    curve: activityValueToCurveSnapshot(e.value),
    label: e.label,
  }));
  if (curves.every((c) => !c.curve)) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }
  const unit = entries.find((e) => e.value?.unit)?.value?.unit ?? null;
  return <DoseResponseFigure curves={curves} size={size} unit={unit} />;
}
