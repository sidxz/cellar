"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { Fragment, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type BoxHoverPoint, boxSummary, hoverInfo } from "../../lib/traces/hover";
import type { Dataset } from "../../types";

/** The part of a Plotly hover event the card reads. */
type HoverEvent = {
  event?: { clientX?: number; clientY?: number };
  points?: (BoxHoverPoint & { customdata?: unknown; hoverOnBox?: boolean })[];
};

/** The cursor, in window coordinates, and what it hovers. */
type Shown = { x: number; y: number } & ({ row: number } | { box: BoxHoverPoint[] });

/** Between the cursor and the card. */
const GAP = 12;
/** Between the card and the window's edges. */
const EDGE = 8;
const STRUCTURE = 120;

/** Where a card ``size`` long goes on one axis of a window ``extent`` long, the cursor at
 * ``at``: just past the cursor when it fits, else just before it — and never outside. */
function place(at: number, size: number, extent: number): number {
  const past = at + GAP;
  const start = past + size <= extent - EDGE ? past : at - GAP - size;
  return Math.max(EDGE, Math.min(start, extent - EDGE - size));
}

/** The hovered compound's structure. Moving on to the next compound keeps the last drawing
 * on screen until the next one is drawn, so the card never flashes blank between points. */
function CardStructure({ smiles }: { smiles: string }) {
  const [drawn, setDrawn] = useState(smiles);
  // Keyed by SMILES, so the drawing on screen stays mounted (and drawn) beside the next.
  const layers = drawn === smiles ? [smiles] : [drawn, smiles];
  return (
    <div className="relative mx-auto" style={{ width: STRUCTURE, height: STRUCTURE }}>
      {layers.map((s) => (
        <div
          key={s}
          className="absolute inset-0"
          style={s === drawn ? undefined : { opacity: 0 }}
          // React's load event bubbles: the next drawing is ready once its image has loaded.
          onLoad={s === drawn ? undefined : () => setDrawn(s)}
        >
          <StructureThumbnail smiles={s} size={STRUCTURE} />
        </div>
      ))}
    </div>
  );
}

/** A plot's hover card: Plotly hover labels are SVG text and cannot draw a structure, so
 * points whose traces carry their row (``customdata``) and ``hoverinfo: "none"`` show this
 * card next to the cursor instead — the compound's structure, its place and ``fields`` —
 * and a hovered box its median, quartiles, fences and range. Only the hovered row is ever
 * rendered. The card sits over the page (not in the panel), measured and kept whole inside
 * the window. Spread ``handlers`` on the Plot and put ``card`` in the element ``ref`` names. */
export function useHoverCard(ds: Dataset, fields: (string | undefined)[]) {
  const ref = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const handlers = {
    onHover: (ev: unknown) => {
      const { event, points = [] } = ev as HoverEvent;
      const box = ref.current?.getBoundingClientRect();
      const p = points[0];
      if (!box || !p) return;
      const at = { x: event?.clientX ?? box.left, y: event?.clientY ?? box.top };
      // A box's stats name the box's first point too: hoverOnBox decides.
      if (p.hoverOnBox) setShown({ ...at, box: points.filter((q) => q.hoverOnBox) });
      else if (typeof p.customdata === "number") setShown({ ...at, row: p.customdata });
      else setShown(null);
    },
    onUnhover: () => setShown(null),
  };

  // Placed once its size is known, before the browser paints it.
  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el || !shown) return;
    const { width, height } = el.getBoundingClientRect();
    el.style.left = `${place(shown.x, width, window.innerWidth)}px`;
    el.style.top = `${place(shown.y, height, window.innerHeight)}px`;
    el.style.visibility = "visible";
  }, [shown]);

  let card = null;
  if (shown) {
    const info = "row" in shown ? hoverInfo(ds, shown.row, fields) : null;
    const { title, lines } = info ?? boxSummary("box" in shown ? shown.box : []);
    card = createPortal(
      <div
        ref={cardRef}
        role="tooltip"
        style={{ left: 0, top: 0, visibility: "hidden" }}
        className="pointer-events-none fixed z-50 w-56 rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md"
      >
        {info?.structure && <CardStructure smiles={info.structure} />}
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
      </div>,
      document.body,
    );
  }
  return { ref, handlers, card };
}
