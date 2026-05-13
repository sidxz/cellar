"use client";

import dynamic from "next/dynamic";
import type { ComponentType, CSSProperties } from "react";

/** Loose Plotly props.
 *
 * @types/react-plotly.js transitively requires @types/plotly.js, which is not
 * installed in this project. Rather than pull in the full types (which also
 * reject several runtime-valid layout/config shapes the app uses today), we
 * re-declare a loose shape here. This still removes the per-call-site
 * `as any` casts and gives autocomplete on the well-typed props (style,
 * useResizeHandler). The object-typed props accept any plain object literal. */
export interface PlotProps {
  data: ReadonlyArray<Record<string, unknown>>;
  layout: Record<string, unknown>;
  config?: Record<string, unknown>;
  style?: CSSProperties;
  useResizeHandler?: boolean;
  onClick?: (event: unknown) => void;
  className?: string;
}

/** SSR-disabled Plotly component. Centralizing the dynamic import here
 * removes per-call-site `as any` casts and keeps the ssr-skip behavior
 * consistent across the app. */
export const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
}) as ComponentType<PlotProps>;

/** Subset of the runtime Plotly namespace exposed on `window` after the
 * react-plotly.js bundle loads. Used for imperative side-channel calls
 * (downloadImage etc.) that aren't wrapped by react-plotly.js props. */
interface PlotlyGlobal {
  downloadImage?: (
    el: HTMLElement,
    opts: { format: "png" | "svg" | "jpeg" | "webp"; width: number; height: number; filename: string },
  ) => void;
}

export function getPlotlyGlobal(): PlotlyGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Plotly?: PlotlyGlobal }).Plotly;
}
