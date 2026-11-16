"use client";

/**
 * DoseResponseFigure — cellar's binding of the suite's canonical curve
 * renderer to cellar's Plotly instance.
 *
 * The renderer itself lives in `@structflo/components/dose-response` so
 * daikon and prot-cellar draw the identical picture from the identical
 * `curve_snapshot`. It takes the Plotly component as a prop (plotly.js
 * touches `document` at import, so each app owns its own client-only
 * wrapper); supplying that here keeps every call site in cellar unchanged.
 */

import {
  type DoseResponseChartViewProps,
  type DoseResponseFigureProps,
  DoseResponseChartView as SharedDoseResponseChartView,
  DoseResponseFigure as SharedDoseResponseFigure,
} from "@structflo/components/dose-response";
import { useMemo } from "react";

import { Plot } from "@/shared/lib/plotly";
import { withFitNotes } from "../lib/dose-response-display";

export type {
  AdditionalCurve,
  AggregateMarker,
  CurvePoint,
  CurveSnapshot,
  FigureSize,
} from "@structflo/components/dose-response";

export function DoseResponseFigure(props: Omit<DoseResponseFigureProps, "plot">) {
  return <SharedDoseResponseFigure {...props} plot={Plot} />;
}

/** The suite's whole chart (toggles, export, plot, a summary card per curve) on cellar's
 *  Plotly, with cellar's fit notes worded on the cards. */
export function DoseResponseChartView({
  curves,
  ...props
}: Omit<DoseResponseChartViewProps, "plot">) {
  const worded = useMemo(() => curves.map(withFitNotes), [curves]);
  return <SharedDoseResponseChartView {...props} curves={worded} plot={Plot} />;
}
