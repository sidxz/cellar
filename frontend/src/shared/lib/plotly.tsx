"use client";

import dynamic from "next/dynamic";
import { type CSSProperties, type ComponentType, useMemo } from "react";

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
 * here, so it is switched off once for all of them. */
export function Plot({ config, ...props }: PlotProps) {
  const safeConfig = useMemo(() => ({ ...config, showSendToCloud: false }), [config]);
  return <PlotlyPlot {...props} config={safeConfig} />;
}

/** Subset of the runtime Plotly namespace exposed on `window` after the
 * react-plotly.js bundle loads. Used for imperative side-channel calls
 * (downloadImage etc.) that aren't wrapped by react-plotly.js props. */
interface PlotlyGlobal {
  /** Takes a drawn graph element, or a figure object to render off-screen. */
  downloadImage?: (
    el:
      | HTMLElement
      | { data: ReadonlyArray<Record<string, unknown>>; layout: Record<string, unknown> },
    opts: {
      format: "png" | "svg" | "jpeg" | "webp";
      width: number;
      height: number;
      filename: string;
    },
  ) => void;
}

export function getPlotlyGlobal(): PlotlyGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Plotly?: PlotlyGlobal }).Plotly;
}
