"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import type { ColDef } from "ag-grid-community";
import { useMemo } from "react";
import type { CurvePosition } from "../lib/curve-plot";
import { type WindowRow, concentrationSeries, windowRows } from "../lib/melt-results";
import type { MeltWindow, StepCheck } from "../types";

const COLUMNS: ColDef<WindowRow>[] = [
  { headerName: "Position", field: "position", minWidth: 120 },
  { headerName: "Role", field: "role", width: 140 },
  { headerName: "Batch", field: "batch", width: 120 },
  { headerName: "Concentration", field: "concentration", width: 130 },
  { headerName: "Tm (°C)", field: "tm", width: 100, valueFormatter: (p) => fmt(p.value) },
  {
    headerName: "ΔTm (°C)",
    field: "deltaTm",
    width: 110,
    sortable: true,
    valueFormatter: (p) => fmt(p.value),
  },
  { headerName: "Flags", field: "flags", flex: 1, minWidth: 220, sortable: true },
];
const fmt = (v: number | null) => (v == null ? "" : v.toFixed(1));

/** Per temperature window: Tm and ΔTm per position, and ΔTm against
 *  concentration (no fit) for dose series. */
export function MeltWindowResults({
  windows,
  positions,
  checks,
  doseUnit,
}: {
  windows: MeltWindow[];
  positions: CurvePosition[];
  checks: StepCheck[];
  doseUnit: string;
}) {
  const referencesDiffer = checks.some((c) => c.references_differ);
  return (
    <div className="space-y-6">
      {referencesDiffer && (
        <p className="text-sm text-muted-foreground">References differ in their number of steps</p>
      )}
      {windows.map((w) => (
        <WindowSection
          key={`${w.channel_key}/${w.window}`}
          window={w}
          positions={positions}
          checks={checks}
          doseUnit={doseUnit}
        />
      ))}
    </div>
  );
}

function WindowSection({
  window: w,
  positions,
  checks,
  doseUnit,
}: {
  window: MeltWindow;
  positions: CurvePosition[];
  checks: StepCheck[];
  doseUnit: string;
}) {
  const rows = useMemo(() => windowRows(w, positions, checks), [w, positions, checks]);
  const series = useMemo(
    () => (w.delta_tm_readout_id ? concentrationSeries(w, positions) : []),
    [w, positions],
  );
  // Ticks at the measured concentrations: Plotly's default log ticks label 20–50 as "2 3 4 5".
  const doses = useMemo(
    () => [...new Set(series.flatMap((s) => s.points.map((p) => p.dose)))].sort((a, b) => a - b),
    [series],
  );
  const columns = useMemo(
    () => (w.delta_tm_readout_id ? COLUMNS : COLUMNS.filter((c) => c.field !== "deltaTm")),
    [w.delta_tm_readout_id],
  );
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">{`${w.window} (${w.low}–${w.high} °C)`}</h3>
      <p className="text-sm text-muted-foreground">
        {w.reference_tm == null
          ? "No reference value in this window"
          : `Reference Tm ${w.reference_tm.toFixed(1)} °C from ${w.reference_count} position${w.reference_count === 1 ? "" : "s"}`}
      </p>
      <DataGrid
        rowData={rows}
        columnDefs={columns}
        height={Math.min(400, 80 + rows.length * 42)}
        suppressFilters
      />
      {series.length > 0 && (
        <Plot
          style={{ width: "100%", height: 320 }}
          useResizeHandler
          data={series.map((s, i) => ({
            type: "scatter",
            mode: "markers",
            name: s.batchLabel,
            x: s.points.map((p) => p.dose),
            y: s.points.map((p) => p.deltaTm),
            marker: { color: GROUP_PALETTE[i % GROUP_PALETTE.length], size: 8 },
          }))}
          layout={{
            margin: { t: 16, r: 16, b: 48, l: 56 },
            xaxis: {
              type: "log",
              title: { text: `Concentration (${doseUnit})` },
              tickvals: doses,
              ticktext: doses.map(String),
            },
            yaxis: { title: { text: "ΔTm (°C)" }, zeroline: false },
            shapes: [
              {
                type: "line",
                xref: "paper",
                x0: 0,
                x1: 1,
                y0: 0,
                y1: 0,
                line: { dash: "dot", width: 1 },
              },
            ],
            annotations: [
              {
                xref: "paper",
                x: 1,
                y: 0,
                text: "Reference",
                showarrow: false,
                xanchor: "right",
                yanchor: "bottom",
              },
            ],
          }}
        />
      )}
    </section>
  );
}
