"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { type CSSProperties, Fragment, useRef, useState } from "react";
import { type BoxHoverPoint, boxSummary, hoverInfo } from "../../lib/traces/hover";
import type { Dataset } from "../../types";

/** The part of a Plotly hover event the card reads. */
type HoverEvent = {
  event?: { clientX?: number; clientY?: number };
  points?: (BoxHoverPoint & { customdata?: unknown; hoverOnBox?: boolean })[];
};

type Shown = { x: number; y: number; w: number; h: number } & (
  | { row: number }
  | { box: BoxHoverPoint[] }
);

const GAP = 12;

/** A plot's hover card: Plotly hover labels are SVG text and cannot draw a structure, so
 * points whose traces carry their row (``customdata``) and ``hoverinfo: "none"`` show this
 * card next to the cursor instead — the compound's structure, its place and ``fields`` —
 * and a hovered box its median and quartiles. Only the hovered row is ever rendered.
 * Spread ``handlers`` on the Plot and put ``card`` in the element ``ref`` names. */
export function useHoverCard(ds: Dataset, fields: (string | undefined)[]) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const handlers = {
    onHover: (ev: unknown) => {
      const { event, points = [] } = ev as HoverEvent;
      const box = ref.current?.getBoundingClientRect();
      const p = points[0];
      if (!box || !p) return;
      const at = {
        x: (event?.clientX ?? box.left) - box.left,
        y: (event?.clientY ?? box.top) - box.top,
        w: box.width,
        h: box.height,
      };
      // A box's stats name the box's first point too: hoverOnBox decides.
      if (p.hoverOnBox) setShown({ ...at, box: points.filter((q) => q.hoverOnBox) });
      else if (typeof p.customdata === "number") setShown({ ...at, row: p.customdata });
      else setShown(null);
    },
    onUnhover: () => setShown(null),
  };

  let card = null;
  if (shown) {
    // Toward the roomier side of the cursor, so the card stays inside the panel.
    const style: CSSProperties = {
      ...(shown.x > shown.w / 2 ? { right: shown.w - shown.x + GAP } : { left: shown.x + GAP }),
      ...(shown.y > shown.h / 2 ? { bottom: shown.h - shown.y + GAP } : { top: shown.y + GAP }),
    };
    const info = "row" in shown ? hoverInfo(ds, shown.row, fields) : null;
    const { title, lines } = info ?? boxSummary("box" in shown ? shown.box : []);
    card = (
      <div
        role="tooltip"
        style={style}
        className="pointer-events-none absolute z-20 w-56 rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md"
      >
        {info?.structure && (
          <StructureThumbnail smiles={info.structure} size={120} className="mx-auto" />
        )}
        <p className="font-medium">{title}</p>
        {info?.place && <p className="text-muted-foreground">{info.place}</p>}
        {lines.length > 0 && (
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            {lines.map((l) => (
              <Fragment key={l.label}>
                <dt className="text-muted-foreground">{l.label}</dt>
                <dd className="text-right tabular-nums">{l.value}</dd>
              </Fragment>
            ))}
          </dl>
        )}
      </div>
    );
  }
  return { ref, handlers, card };
}
