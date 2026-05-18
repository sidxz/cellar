"use client";

import { useMemo } from "react";
import { Plot } from "@/shared/lib/plotly";
import type {
  ClusterAssignment,
  RepresentativePick,
  UmapPoint,
} from "@/features/sar-analysis/types";
import {
  colorForPoint,
  type ColorOption,
} from "@/features/sar-analysis/lib/cluster-palette";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ClusterScatterProps {
  points: UmapPoint[];
  clusters: ClusterAssignment[];
  representatives: RepresentativePick[];
  colorMode: ColorOption;
  activityPic50: Record<string, number | null>;
  scaffoldByMol: Record<string, string | null>;
  /** Chemist-readable hover label per molecule id, e.g. "CV-00984 · SACC-0460144". */
  labelByMolId?: Record<string, string>;
  onSelected: (polygon: { x: number; y: number }[] | null) => void;
  onPointClick: (moleculeId: string) => void;
  lassoActive?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * ClusterScatter — Plotly scattergl scatter for the UMAP cluster map view.
 *
 * Two overlaid traces:
 *   1. Base points — colored by colorMode via colorForPoint (cluster / activity /
 *      scaffold / none).  Uses scattergl for GPU-accelerated rendering at 10K+
 *      points.
 *   2. Star markers for representative picks — rendered on top with a hollow
 *      white star outline so they're always visible regardless of the base
 *      color. Only present when `representatives.length > 0`.
 *
 * Plotly lasso note: the `onSelected` Plotly event carries `ev.lassoPoints`
 * (an {x, y} array) when the user drags a lasso shape. Box-select mode
 * carries `ev.range` instead. We detect lasso via `ev.lassoPoints?.x` and
 * prefer it; if the actual event payload doesn't match this shape on a given
 * Plotly version, `polygon` will be null — callers should handle null as
 * "deselect / no polygon".
 */
export function ClusterScatter({
  points,
  clusters,
  representatives,
  colorMode,
  activityPic50,
  scaffoldByMol,
  labelByMolId,
  onSelected,
  onPointClick,
}: ClusterScatterProps) {
  // Build mol → clusterId lookup once.
  const clusterById = useMemo(
    () => new Map(clusters.map((c) => [c.moleculeId, c.clusterId])),
    [clusters],
  );

  // Per-point fill color array for the base trace.
  const fillColors = useMemo(
    () =>
      points.map((p) =>
        colorForPoint(colorMode, {
          clusterId: clusterById.get(p.moleculeId) ?? 0,
          activityPic50: activityPic50[p.moleculeId] ?? null,
          scaffoldId: scaffoldByMol[p.moleculeId] ?? null,
        }),
      ),
    [points, colorMode, clusterById, activityPic50, scaffoldByMol],
  );

  // --- Traces ---

  const baseTrace: Record<string, unknown> = {
    type: "scattergl",
    mode: "markers",
    x: points.map((p) => p.x),
    y: points.map((p) => p.y),
    marker: {
      color: fillColors,
      size: 8,
      line: { width: 0.5, color: "#fff" },
    },
    // customdata carries [moleculeId, hoverLabel] so click handlers get the id
    // while hovertemplate displays the chemist-readable label.
    customdata: points.map((p) => [
      p.moleculeId,
      labelByMolId?.[p.moleculeId] ?? p.moleculeId,
    ]),
    hovertemplate: "%{customdata[1]}<extra></extra>",
  };

  const repIds = new Set(representatives.map((r) => r.moleculeId));
  const repPoints = points.filter((p) => repIds.has(p.moleculeId));

  const starTrace: Record<string, unknown> | null =
    representatives.length > 0
      ? {
          type: "scattergl",
          mode: "markers",
          x: repPoints.map((p) => p.x),
          y: repPoints.map((p) => p.y),
          marker: {
            symbol: "star",
            size: 16,
            color: "rgba(0,0,0,0)",
            line: { width: 1.5, color: "#ffffff" },
          },
          hoverinfo: "skip",
        }
      : null;

  const data = starTrace ? [baseTrace, starTrace] : [baseTrace];

  // PlotProps.onClick / onSelected are not declared on the shared PlotProps
  // interface (which is intentionally loose). We pass them via a cast so the
  // shared dynamic-import wrapper handles the event wiring correctly.
  const extraHandlers = {
    onSelected: (ev: any) => {
      if (!ev) {
        onSelected(null);
        return;
      }
      // Lasso: ev.lassoPoints = {x: number[], y: number[]}
      // Box: ev.range = {x: [min,max], y: [min,max]} (no polygon)
      const lasso = ev.lassoPoints as { x: number[]; y: number[] } | undefined;
      if (lasso?.x) {
        const polygon = lasso.x.map((x: number, i: number) => ({
          x,
          y: lasso.y[i],
        }));
        onSelected(polygon);
      } else {
        onSelected(null);
      }
    },
    onClick: (ev: any) => {
      const pt = ev?.points?.[0];
      const cd = pt?.customdata;
      // customdata is [moleculeId, hoverLabel]; click handler wants the id.
      const moleculeId = Array.isArray(cd) ? (cd[0] as string) : (cd as string | undefined);
      if (moleculeId) onPointClick(moleculeId);
    },
  };

  return (
    <Plot
      data={data}
      layout={{
        autosize: true,
        margin: { l: 24, r: 8, t: 8, b: 24 },
        xaxis: { showgrid: false, zeroline: false, visible: false },
        yaxis: { showgrid: false, zeroline: false, visible: false },
        dragmode: "lasso",
        showlegend: false,
      }}
      config={{
        displaylogo: false,
        modeBarButtonsToRemove: [
          "zoom2d",
          "select2d",
          "zoomIn2d",
          "zoomOut2d",
          "autoScale2d",
          "resetScale2d",
        ],
      }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      {...(extraHandlers as any)}
    />
  );
}
