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
  type DoseResponseFigureProps,
  DoseResponseFigure as SharedDoseResponseFigure,
} from "@structflo/components/dose-response";

import { Plot } from "@/shared/lib/plotly";

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
