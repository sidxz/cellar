"use client";

import {
  type CurveSnapshot,
  DoseResponseFigure,
} from "@/features/screening-assay/components/dose-response-figure";
import { memo } from "react";
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
  if (
    !value ||
    !value.raw_data ||
    value.raw_data.length === 0 ||
    value.source !== "dose_response" ||
    value.curve_params == null ||
    value.value == null
  ) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }

  const curve: CurveSnapshot = {
    fitted_value: value.value,
    top: value.curve_params.top,
    bottom: value.curve_params.bottom,
    hill_slope: value.curve_params.hill_slope,
    r_squared: value.r_squared,
    curve_class: value.curve_params.curve_class ?? null,
    raw_data: value.raw_data,
    // Aggregate-mode overlay — when the cell collapses N runs via mean /
    // gmean, the BE writes the other contributors + an explicit marker so
    // the chart can overlay them muted and draw a single vertical line at
    // the cell's aggregate value. Absent on LATEST / BEST_R_SQUARED cells.
    additional_curves: value.additional_curves ?? null,
    aggregate: value.aggregate ?? null,
  };

  return <DoseResponseFigure curve={curve} size="cell" unit={value.unit ?? null} />;
}

export const DoseResponseCell = memo(DoseResponseCellInner);
