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
import {
  hasSelectionGeometry,
  selectedIdsFromPlotlyEvent,
} from "@/features/sar-analysis/lib/lasso-math";
import { buildOverlayTraces } from "@/features/sar-analysis/lib/cluster-overlay";

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
  /** Chemist-readable hover label per molecule id, e.g. "CC-000984 · SACC-0460144". */
  labelByMolId?: Record<string, string>;
  /** IDs currently lassoed — when non-empty, non-lassoed points dim to 0.35
   *  opacity so the chemist can see what they selected on the map. */
  lassoedIds?: Set<string>;
  /** Molecule ids currently in the cherry-pick basket — drawn as emerald rings. */
  basketIds?: Set<string>;
  /** Region diverse-pick candidates — drawn as violet open stars. */
  regionPickIds?: Set<string>;
  /** Fires with the array of selected molecule IDs after a lasso / box selection,
   *  or null when the selection is cleared. */
  onSelected: (moleculeIds: string[] | null) => void;
  onPointClick: (moleculeId: string) => void;
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
  lassoedIds,
  basketIds,
  regionPickIds,
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

  // Trace type: prefer SVG `scatter` for ≤5K points. Plotly's `scattergl`
  // (WebGL) historically does not thread `customdata` reliably into
  // `plotly_selected` event payloads — the lasso fires but the chemist's
  // selection is lost. Below the SVG cutoff, SVG is plenty fast and
  // selection event data is well-defined.
  const useWebGL = points.length > 5000;
  const traceType = useWebGL ? "scattergl" : "scatter";

  // Per-point opacity for lasso visual feedback: lassoed points stay fully
  // opaque, non-lassoed points dim to 0.25 so the chemist can SEE what they
  // selected. When no lasso is active, all points are fully opaque.
  const hasLasso = (lassoedIds?.size ?? 0) > 0;
  const opacities = hasLasso
    ? points.map((p) => (lassoedIds!.has(p.moleculeId) ? 1.0 : 0.25))
    : points.map(() => 1.0);

  const baseTrace: Record<string, unknown> = {
    type: traceType,
    mode: "markers",
    x: points.map((p) => p.x),
    y: points.map((p) => p.y),
    marker: {
      color: fillColors,
      size: 8,
      // Per-marker opacity for lasso dim; broken on scattergl in some versions
      // but works cleanly on SVG `scatter` which is our default for <5K points.
      opacity: opacities,
      line: { width: 0.5, color: "#fff" },
    },
    // customdata carries [moleculeId, hoverLabel] for hovertemplate + click
    // handlers; selection uses pointNumber index lookup against `points` so
    // it works regardless of whether scattergl threads customdata through.
    customdata: points.map((p) => [
      p.moleculeId,
      labelByMolId?.[p.moleculeId] ?? p.moleculeId,
    ]),
    hovertemplate: "%{customdata[1]}<extra></extra>",
  };

  const repIds = new Set(representatives.map((r) => r.moleculeId));
  const repPoints = points.filter((p) => repIds.has(p.moleculeId));

  // Star fill = the representative's chemotype color (cluster palette) so the
  // chemist can identify both "this is a pick" (star shape) AND "from cluster
  // X" (fill color). We force `mode: "cluster"` here so the star always carries
  // chemotype identity even when the base points are colored by Activity /
  // Scaffold / None.
  const starFillColors = repPoints.map((p) =>
    colorForPoint(
      { mode: "cluster" },
      {
        clusterId: clusterById.get(p.moleculeId) ?? 0,
        activityPic50: null,
        scaffoldId: null,
      },
    ),
  );

  const starTrace: Record<string, unknown> | null =
    representatives.length > 0
      ? {
          type: traceType,
          mode: "markers",
          x: repPoints.map((p) => p.x),
          y: repPoints.map((p) => p.y),
          marker: {
            symbol: "star",
            // 12px matches the base 8px dot's visual footprint (stars need a
            // few extra px because of their pointed silhouette / negative space).
            size: 12,
            color: starFillColors,
            // Dark outline so the star stays visible no matter which cluster
            // color it's drawn in. Thicker than the base trace's 0.5px.
            line: { width: 1, color: "#1f2937" },
          },
          hoverinfo: "skip",
        }
      : null;

  const overlayTraces = buildOverlayTraces(
    points,
    basketIds,
    regionPickIds,
    traceType,
  );
  const data = [
    baseTrace,
    ...(starTrace ? [starTrace] : []),
    ...overlayTraces,
  ];

  // PlotProps.onClick / onSelected are not declared on the shared PlotProps
  // interface (which is intentionally loose). We pass them via a cast so the
  // shared dynamic-import wrapper handles the event wiring correctly.
  const extraHandlers = {
    // Plotly fires plotly_selected with ev.points after lasso/box selection.
    // We resolve molecule IDs via `pointNumber` (the trace's array index) and
    // look up our `points` array directly — this is more reliable than
    // `customdata` (which scattergl traces sometimes don't thread through to
    // selection events) and works on both `scatter` and `scattergl` traces.
    // We only honor selections on the BASE trace (curveNumber === 0); stars
    // on curveNumber === 1 don't carry molecule identity in any structured
    // way and would double-count selections.
    onSelected: (ev: any) => {
      // react-plotly.js calls Plotly.react() on every render (our data/layout
      // are new objects each time), and each redraw RE-EMITS plotly_selected
      // with an empty, geometry-less payload. Acting on that artifact would wipe
      // the selection the user just made — so ignore geometry-less events. A
      // genuine clear arrives via onDeselect (double-click).
      if (!hasSelectionGeometry(ev)) return;
      // Resolve via data-space geometry (robust on scatter + scattergl).
      const ids = selectedIdsFromPlotlyEvent(ev, points);
      onSelected(ids.length > 0 ? ids : null);
    },
    // Plotly fires plotly_deselect when user double-clicks outside a selection.
    onDeselect: () => onSelected(null),
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
        // Preserve the user's lasso selection across Plotly.react() redraws.
        // react-plotly.js redraws on every render (our data/layout are new
        // objects each time); without a stable uirevision, each redraw clears
        // the selection and emits a spurious empty plotly_selected + a
        // plotly_deselect, which wiped lassoedIds a frame after it was set.
        // selectionrevision defaults to uirevision, so a constant value here
        // keeps the selection (and zoom/pan) stable. See plotly.js layout ref
        // + react-plotly.js#147. Bump this string to intentionally reset state.
        uirevision: "cluster-map",
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
