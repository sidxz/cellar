"use client";

import { Skeleton } from "@/shared/components/ui/skeleton";
import { Plot } from "@/shared/lib/plotly";
import { cn } from "@/shared/lib/utils";
import { useQueries } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { type CurveView, runCurvesQuery } from "../hooks/use-run-curves";
import {
  type CurveBand,
  type CurveSet,
  type PlotStep,
  buildCurveFigure,
  curveSetFromRun,
  focusIdFromHover,
} from "../lib/curve-plot";
import type { RunCurves } from "../types";
import type { CurveDraw } from "./curve-viewer";

/** A panel is its caption line over its plot: 120 px. */
const CAPTION = 16;
const PLOT = 104;
const MARGIN = 6;
/** More under the bottom panel, for the temperature axis. */
const AXIS = 38;
// A double-click always shows all: the range a plot was first drawn with is
// not what a reset goes back to, so the button that returns to it is left out.
const PLOT_CONFIG = {
  displaylogo: false,
  responsive: true,
  doubleClick: "autosize",
  modeBarButtonsToRemove: ["resetScale2d"],
};
const PLOT_STYLE = { width: "100%", height: PLOT };
const AXIS_PLOT_STYLE = { width: "100%", height: PLOT + AXIS };
const PLACEHOLDER =
  "flex items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground";
/** Per signal, top to bottom. */
const VIEWS: readonly CurveView[] = ["derivative", "measured"];

/** What the single view draws on one signal beside its traces. */
export interface SignalMarks {
  steps?: ReadonlyMap<string, readonly PlotStep[]>;
  windows?: readonly CurveBand[];
}

export interface AllSignalsPlotProps {
  runId: string;
  /** The run's signals, in the signal switch's order. */
  signals: CurveSet["channels"];
  /** What the single view asks for a signal's view, so both read one cache. */
  request: (
    signal: string,
    view: CurveView,
  ) => { channel?: string; view: CurveView; window?: number };
  /** By signal key. */
  marks: ReadonlyMap<string, SignalMarks>;
  draw: CurveDraw;
  /** The smoothing the derivatives were calculated with, as the API reports it. */
  onWindow: (window: number | null) => void;
}

/** Every signal of the run at once: per signal its derivative over its
 *  measured trace, stacked on one temperature axis. Each panel is the single
 *  view's figure for that signal and view; a zoom or pan of the temperature
 *  axis on one panel moves them all. Read only: nothing is picked here. */
export function AllSignalsPlot({
  runId,
  signals,
  request,
  marks,
  draw,
  onWindow,
}: AllSignalsPlotProps) {
  const panels = signals.flatMap((signal) => VIEWS.map((view) => ({ signal, view })));
  const queries = useQueries({
    queries: panels.map((p) => runCurvesQuery(runId, request(p.signal.key, p.view))),
  });
  // The temperature range zoomed or panned to on any panel; null shows all.
  // Each reset counts, so every panel then draws both its axes anew.
  const [zoom, setZoom] = useState<{ range: readonly [number, number] | null; resets: number }>({
    range: null,
    resets: 0,
  });
  const onRelayout = useCallback((ev: unknown) => {
    const change = (ev ?? {}) as Record<string, unknown>;
    const low = change["xaxis.range[0]"];
    const high = change["xaxis.range[1]"];
    if (typeof low === "number" && typeof high === "number")
      setZoom((z) => ({ ...z, range: [low, high] }));
    else if (change["xaxis.autorange"]) setZoom((z) => ({ range: null, resets: z.resets + 1 }));
  }, []);

  const smoothing =
    queries.find((q, i) => panels[i].view === "derivative" && q.data)?.data?.window ?? null;
  useEffect(() => onWindow(smoothing), [smoothing, onWindow]);

  if (queries.some((q) => q.isLoading))
    return (
      <Skeleton
        data-testid="all-signals-loading"
        className="w-full"
        style={{ height: panels.length * (CAPTION + PLOT) + AXIS }}
      />
    );

  // All the drawn traces cover, over every panel, and the last panel that draws any.
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  let last = -1;
  queries.forEach((q, i) => {
    for (const curve of q.data?.curves ?? []) {
      if (!draw.drawn.has(curve.well_id)) continue;
      last = i;
      for (const x of curve.x) {
        if (x < low) low = x;
        if (x > high) high = x;
      }
    }
  });
  const [from, to] = zoom.range ?? (low < high ? [low, high] : [null, null]);

  return (
    <section aria-label="All signals" className="space-y-2">
      <div>
        {panels.map((p, i) => {
          const { data, isPlaceholderData } = queries[i];
          return (
            <figure key={`${p.signal.key}:${p.view}`}>
              <figcaption className="pl-16 text-xs font-medium leading-4 text-muted-foreground">
                {p.view === "derivative" ? `${p.signal.label} · d/dT` : p.signal.label}
              </figcaption>
              {data ? (
                <SignalPanel
                  data={data}
                  marks={marks.get(p.signal.key)}
                  draw={draw}
                  from={from}
                  to={to}
                  resets={zoom.resets}
                  axis={i === last}
                  pending={isPlaceholderData}
                  onRelayout={onRelayout}
                />
              ) : (
                <p className={PLACEHOLDER} style={{ height: PLOT }}>
                  Could not load the traces. Reload the page and try again.
                </p>
              )}
            </figure>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        To pick or edit a peak on the plot, choose one signal.
      </p>
    </section>
  );
}

function SignalPanel({
  data,
  marks,
  draw,
  from,
  to,
  resets,
  axis,
  pending,
  onRelayout,
}: {
  data: RunCurves;
  marks: SignalMarks | undefined;
  draw: CurveDraw;
  /** The temperature range every panel shows; null leaves it to the plot. */
  from: number | null;
  to: number | null;
  resets: number;
  /** The bottom panel: it titles and numbers the temperature axis. */
  axis: boolean;
  pending: boolean;
  onRelayout: (ev: unknown) => void;
}) {
  // The trace under the pointer, on this panel only; as in the single view.
  const [hovered, setHovered] = useState<string | null>(null);
  const onHover = useCallback(
    (ev: unknown) => flushSync(() => setHovered(focusIdFromHover(ev))),
    [],
  );
  const onUnhover = useCallback(() => flushSync(() => setHovered(null)), []);
  const set = useMemo(() => curveSetFromRun(data), [data]);
  const { drawn, showReported, colouring } = draw;
  const steps = marks?.steps;
  const windows = marks?.windows;
  // Memoised on its real inputs, as the single view's: Plotly is handed a new
  // figure only when something it draws changed.
  const figure = useMemo(() => {
    const single = buildCurveFigure({
      set,
      drawn,
      showReported,
      canvas: "screen",
      steps,
      windows,
      ...colouring,
      focusedId: hovered ?? colouring.focusedId,
    });
    const xaxis = single.layout.xaxis as Record<string, unknown>;
    const yaxis = single.layout.yaxis as Record<string, unknown>;
    return {
      data: single.data,
      layout: {
        ...single.layout,
        margin: {
          ...(single.layout.margin as Record<string, unknown>),
          t: MARGIN,
          b: axis ? MARGIN + AXIS : MARGIN,
        },
        xaxis: {
          ...xaxis,
          ...(!axis && { title: { text: "" }, showticklabels: false }),
          ...(from !== null && to !== null && { range: [from, to] }),
          // The range is this component's: after a reset Plotly's own goes.
          uirevision: `x:${resets}`,
        },
        // The caption names the signal.
        yaxis: { ...yaxis, title: { text: "" }, uirevision: `${yaxis.uirevision}:${resets}` },
      },
    };
  }, [set, drawn, showReported, colouring, hovered, steps, windows, from, to, resets, axis]);

  if (figure.data.length === 0)
    return (
      <p className={PLACEHOLDER} style={{ height: PLOT }}>
        {set.view === "derivative"
          ? "No derivative could be calculated for the selected positions."
          : "The selected positions have no traces for this signal."}
      </p>
    );
  return (
    <div className={cn("transition-opacity", pending && "opacity-60")}>
      <Plot
        data={figure.data}
        layout={figure.layout}
        config={PLOT_CONFIG}
        style={axis ? AXIS_PLOT_STYLE : PLOT_STYLE}
        useResizeHandler
        onHover={onHover}
        onUnhover={onUnhover}
        onRelayout={onRelayout}
      />
    </div>
  );
}
