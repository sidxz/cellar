"use client";

import { StructureThumbnail } from "@/shared/components/chemistry/structure-thumbnail";
import { CHART_AXIS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import { useTheme } from "next-themes";
import { memo, useState } from "react";
import { createPortal } from "react-dom";
import type { Band } from "../lib/melt-hits";
import { type ShiftRow, formatDelta } from "../lib/melt-results";
import { GRID, saveAsSvg, selectedOutline, shiftBand, shiftColour } from "../lib/shift-figure";

/** The hover card's structure box, and the room the card is given beside the cursor. */
const STRUCTURE = { width: 168, height: 96 };
const CARD = { width: 192, height: 168, gap: 12 };

/** What the cursor is over: a Plotly hover label is text and cannot draw a
 *  structure, so the point's own card is shown beside the cursor instead. */
type Hovered = { x: number; y: number; row: ShiftRow };

interface ShiftPlotProps {
  rows: readonly ShiftRow[];
  /** The positions the run's hit rule calls hits. */
  hits: ReadonlySet<string>;
  /** The rule on this window's ΔTm, drawn as a band or line; null draws none. */
  band: Band | null;
  /** The numbers the run's rules compare this window's ΔTm against: a value
   *  beside one is shown to two decimals. */
  limits?: readonly number[];
  selected: ReadonlySet<string>;
  onSelect: (wellId: string) => void;
}

/** The figure alone. Memoized so that showing the hover card does not draw it
 *  again: a redraw makes Plotly forget what is hovered, and it then never
 *  reports the pointer leaving the point. */
const ShiftFigure = memo(function ShiftFigure({
  rows,
  hits,
  band,
  limits,
  selected,
  onSelect,
  onHover,
}: ShiftPlotProps & { onHover: (hovered: Hovered | null) => void }) {
  const { resolvedTheme } = useTheme();
  const longest = Math.max(0, ...rows.map((r) => r.label.length));
  // Room for a registration number with its aliases; the axis grows past this if it must.
  const left = Math.min(280, 40 + longest * 7);
  const { shapes, annotations } = shiftBand(band, "x");
  const plot = (
    <Plot
      data={[
        {
          type: "scatter",
          mode: "markers",
          orientation: "h",
          x: rows.map((r) => r.deltaTm),
          y: rows.map((r) => r.label),
          customdata: rows.map((r) => r.wellId),
          text: rows.map((r) => formatDelta(r.deltaTm, limits)),
          marker: {
            color: rows.map((r) => shiftColour(r.deltaTm, hits.has(r.wellId))),
            size: rows.map((r) => (selected.has(r.wellId) ? 11 : 8)),
            line: {
              width: rows.map((r) => (selected.has(r.wellId) ? 2 : 0)),
              color: selectedOutline(resolvedTheme),
            },
          },
          // The card below stands in for Plotly's label.
          hoverinfo: "none",
        },
      ]}
      layout={{
        autosize: true,
        height: Math.max(240, 22 * rows.length + 60),
        margin: { t: 28, b: 40, l: left, r: 16 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: CHART_AXIS.tick },
        xaxis: { title: { text: "ΔTm (°C)" }, gridcolor: GRID, zeroline: false },
        yaxis: {
          type: "category",
          categoryorder: "array",
          categoryarray: rows.map((r) => r.label),
          gridcolor: GRID,
          automargin: true,
        },
        shapes,
        annotations,
      }}
      config={saveAsSvg("shift-plot")}
      style={{ width: "100%" }}
      onClick={(event) => {
        const id = (event as { points: { customdata?: unknown }[] }).points[0]?.customdata;
        if (typeof id === "string") onSelect(id);
      }}
      onHover={(event) => {
        const { event: at, points } = event as {
          event?: { clientX?: number; clientY?: number };
          points?: { customdata?: unknown }[];
        };
        const row = rows.find((r) => r.wellId === points?.[0]?.customdata);
        onHover(
          row && at?.clientX != null && at.clientY != null
            ? { x: at.clientX, y: at.clientY, row }
            : null,
        );
      }}
      onUnhover={() => onHover(null)}
    />
  );
  // Beyond 60 rows the panel scrolls; the figure keeps its full height inside.
  return rows.length > 60 ? <div style={{ maxHeight: 560, overflowY: "auto" }}>{plot}</div> : plot;
});

export function ShiftPlot(props: ShiftPlotProps) {
  const { limits } = props;
  const [hovered, setHovered] = useState<Hovered | null>(null);
  // ponytail: placed from a fixed card size, past the cursor or before it where it
  // would leave the window; measure the card if its contents grow.
  const card =
    hovered &&
    createPortal(
      <div
        role="tooltip"
        className="pointer-events-none fixed z-50 space-y-1 rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md"
        style={{
          width: CARD.width,
          left:
            hovered.x + CARD.gap + CARD.width > window.innerWidth
              ? hovered.x - CARD.gap - CARD.width
              : hovered.x + CARD.gap,
          top:
            hovered.y + CARD.gap + CARD.height > window.innerHeight
              ? hovered.y - CARD.gap - CARD.height
              : hovered.y + CARD.gap,
        }}
      >
        <p className="break-words font-medium">{hovered.row.label}</p>
        <p className="tabular-nums text-muted-foreground">
          {`ΔTm ${formatDelta(hovered.row.deltaTm, limits)} °C`}
        </p>
        {hovered.row.smiles && (
          <StructureThumbnail
            smiles={hovered.row.smiles}
            size={STRUCTURE.width}
            height={STRUCTURE.height}
            className="rounded bg-white dark:invert-0"
          />
        )}
      </div>,
      document.body,
    );
  return (
    // Leaving the figure always hides the card, whatever Plotly reports.
    <div onMouseLeave={() => setHovered(null)}>
      <ShiftFigure {...props} onHover={setHovered} />
      {card}
    </div>
  );
}
