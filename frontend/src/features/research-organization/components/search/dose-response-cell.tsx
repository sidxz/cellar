"use client";

import { DoseResponseFigure } from "@/features/screening-assay/components/dose-response-figure";
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
