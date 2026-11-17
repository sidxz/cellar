"use client";

import dynamic from "next/dynamic";
import { type CSSProperties, type ComponentType, useEffect, useMemo, useRef } from "react";

/** Loose Plotly props.
 *
 * Rather than lean on the full plotly.js types (which reject several
 * runtime-valid layout/config shapes the app uses today), we re-declare a
 * loose shape here. This still removes the per-call-site
 * `as any` casts and gives autocomplete on the well-typed props (style,
 * useResizeHandler). The object-typed props accept any plain object literal. */
export interface PlotProps {
  data: ReadonlyArray<Record<string, unknown>>;
  layout: Record<string, unknown>;
  config?: Record<string, unknown>;
  style?: CSSProperties;
  useResizeHandler?: boolean;
  onClick?: (event: unknown) => void;
  onHover?: (event: unknown) => void;
  onUnhover?: (event: unknown) => void;
  /** A layout change made on the plot itself: a zoom, a pan, an axis reset. */
  onRelayout?: (event: unknown) => void;
  /** Called once the graph is first drawn, with the graph div. */
  onInitialized?: (figure: unknown, graphDiv: HTMLElement) => void;
  className?: string;
}

const PlotlyPlot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
}) as ComponentType<PlotProps>;

/** SSR-disabled Plotly component. Centralizing the dynamic import here
 * removes per-call-site `as any` casts and keeps the ssr-skip behavior
 * consistent across the app.
 *
 * plotly.js 4 shows a modebar button by default that uploads the figure, and
 * with it the compound data, to cloud.plotly.com. Every chart goes through
 * here, so it is switched off once for all of them.
 *
 * `useResizeHandler` in react-plotly.js follows window resizes only; a graph
 * whose box changes for any other reason (a panel added, closed or maximized,
 * a side sheet opening) would keep its old size. A ResizeObserver on the graph
 * div re-fits it whenever its box changes. */
export function Plot({ config, onInitialized, ...props }: PlotProps) {
  const safeConfig = useMemo(() => ({ ...config, showSendToCloud: false }), [config]);
  const observer = useRef<ResizeObserver | null>(null);
  useEffect(() => () => observer.current?.disconnect(), []);
  const initialized = (figure: unknown, gd: HTMLElement) => {
    onInitialized?.(figure, gd);
    if (!props.useResizeHandler || typeof ResizeObserver === "undefined") return;
    observer.current?.disconnect();
    // The graph was just drawn to its box: only a different (whole-pixel) size needs a fit.
    // That also skips the report every observer makes on observe().
    const px = (r: { width: number; height: number }) =>
      `${Math.round(r.width)}x${Math.round(r.height)}`;
    let drawn = px(gd.getBoundingClientRect());
    // Plots.resize debounces itself; it rejects for a hidden graph, which needs no fit.
    observer.current = new ResizeObserver(([entry]) => {
      const size = px(entry.contentRect);
      if (size === drawn) return;
      drawn = size;
      getPlotlyGlobal()
        ?.Plots?.resize(gd)
        .catch(() => {});
    });
    observer.current.observe(gd);
  };
  return <PlotlyPlot {...props} config={safeConfig} onInitialized={initialized} />;
}

/** Subset of the runtime Plotly namespace exposed on `window` after the
 * react-plotly.js bundle loads. Used for imperative side-channel calls
 * (downloadImage etc.) that aren't wrapped by react-plotly.js props. */
interface PlotlyGlobal {
  Plots?: { resize: (el: HTMLElement) => Promise<unknown> };
  /** Takes a drawn graph element, or a figure object to render off-screen. */
  downloadImage?: (
    el:
      | HTMLElement
      | { data: ReadonlyArray<Record<string, unknown>>; layout: Record<string, unknown> },
    opts: {
      format: "png" | "svg" | "jpeg" | "webp";
      width: number;
      height: number;
      /** Pixel multiplier: the layout stays ``width`` × ``height``. */
      scale?: number;
      filename: string;
    },
  ) => void;
}

export function getPlotlyGlobal(): PlotlyGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Plotly?: PlotlyGlobal }).Plotly;
}
