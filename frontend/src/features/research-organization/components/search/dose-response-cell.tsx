"use client";

import {
  DoseResponseFigure,
  type FigureSize,
} from "@/features/screening-assay/components/dose-response-figure";
import { memo } from "react";
import { activityValueToCurveSnapshot } from "../../lib/activity-curve-snapshot";
import type { ActivityValue } from "../../types";

interface DoseResponseCellProps {
  value?: ActivityValue;
}

/**
 * Search results IC50 plot cell. Hands the (params + raw_data) tuple to
 * the shared <DoseResponseFigure /> so the search drawing matches the
 * protocol Activity tab + the campaign grid 1:1 — same component, same
 * trace builder, same color tokens, same axis-range strategy.
 */
function DoseResponseCellInner({ value }: DoseResponseCellProps) {
  const curve = activityValueToCurveSnapshot(value);
  // `curve` non-null implies `value` non-null (the mapper guards `!av`); the
  // `!value` keeps that provable for the type checker without a `!` assertion.
  if (!curve || !value) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }
  return <DoseResponseFigure curve={curve} size="cell" unit={value.unit ?? null} />;
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
