"use client";

import {
  type PlotlySelectionEvent,
  hasSelectionGeometry,
} from "@/features/sar-analysis/lib/lasso-math";
import { Plot } from "@/shared/lib/plotly";
import { useTheme } from "next-themes";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { usePassMask } from "../../hooks/use-pass-mask";
import { isComparedValue } from "../../lib/cross-protocol";
import { buildOverlays, mergeOverlays } from "../../lib/overlays/build";
import { addMissingStrip } from "../../lib/traces/missing-strip";
import {
  type PointEvent,
  buildScatterBase,
  rowIdsFromEvent,
  selectScatter,
} from "../../lib/traces/scatter";
import { useWorkbench } from "../../store/workbench-context";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { useHoverCard } from "./hover-card";

const CONFIG = { displaylogo: false };

const sameSet = (ids: string[], set: ReadonlySet<string>) =>
  ids.length === set.size && ids.every((id) => set.has(id));

/** The plot's selectionrevision: it moves whenever the selection changes from anywhere
 * but this plot (table, strip, another panel), so Plotly drops its own lasso outline and
 * ``selectedpoints`` decides what is highlighted. ``own`` records a change this plot makes. */
function useSelectionRevision(selection: ReadonlySet<string>) {
  const ref = useRef({ seen: selection, own: null as string[] | null, revision: 0 });
  const r = ref.current;
  if (r.seen !== selection) {
    if (!r.own || !sameSet(r.own, selection)) r.revision += 1;
    r.seen = selection;
    r.own = null;
  }
  return {
    revision: r.revision,
    own: (ids: string[]) => {
      ref.current.own = ids;
    },
  };
}

type Size = { width: number; height: number };

/** ``ref``'s box in 10 px steps while ``on`` (so a drag re-renders rarely), else undefined. */
function useBoxSize(ref: RefObject<HTMLElement | null>, on: boolean): Size | undefined {
  const [size, setSize] = useState<Size>();
  useEffect(() => {
    const el = ref.current;
    if (!on || !el || typeof ResizeObserver === "undefined") return;
    const step = (v: number) => Math.round(v / 10) * 10;
    const observer = new ResizeObserver(([entry]) => {
      const next = { width: step(entry.contentRect.width), height: step(entry.contentRect.height) };
      setSize((s) => (s?.width === next.width && s.height === next.height ? s : next));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, on]);
  return on ? size : undefined;
}

export function ScatterPanel({ panel, ds }: { panel: PanelConfig; ds: Dataset }) {
  const mask = usePassMask(ds);
  const selection = useWorkbench((s) => s.selection);
  const setSelection = useWorkbench((s) => s.setSelection);
  const clearSelection = useWorkbench((s) => s.clearSelection);
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const { revision, own } = useSelectionRevision(selection);
  const hover = useHoverCard(ds, [panel.x, panel.y, ...panel.appearance.tooltip]);
  // Untested strips take room per reason from the plot's real size; other plots never
  // rebuild on a resize.
  const plotBox = useRef<HTMLDivElement>(null);
  const strips =
    !panel.appearance.splitBy && (isComparedValue(ds, panel.x) || isComparedValue(ds, panel.y));
  const size = useBoxSize(plotBox, strips);

  // The costly part (coordinates, colors, hover text, untested strip, overlays) waits for a data or
  // settings change; a selection only lays its marks on top.
  const base = useMemo(() => {
    const base = buildScatterBase(ds, panel, mask, dark);
    const { fig } = addMissingStrip(base, ds, panel, mask, dark, size);
    return mergeOverlays(fig, buildOverlays(ds, panel, mask, fig.facets ?? []));
  }, [ds, panel, mask, dark, size]);
  const fig = useMemo(() => selectScatter(base, ds, selection), [base, ds, selection]);
  // The constant uirevision (in the figure) keeps zoom; selectionrevision governs the lasso.
  const layout = useMemo(
    () => ({ ...fig.layout, selectionrevision: `${panel.id}:${revision}` }),
    [fig.layout, panel.id, revision],
  );

  // Plotly fires these from its own emitter, outside React's batching: flushSync makes
  // the store change render now. Same pattern as the SAR cluster map.
  const select = (ids: string[]) => {
    if (sameSet(ids, selection)) return;
    own(ids);
    flushSync(() => setSelection(ids));
  };
  const handlers = {
    onSelected: (ev: unknown) => {
      // Redraws re-emit plotly_selected without geometry; only a real lasso/box has it.
      if (!hasSelectionGeometry(ev as PlotlySelectionEvent)) return;
      select(rowIdsFromEvent(ds, ev as PointEvent));
    },
    onDeselect: () => {
      if (selection.size === 0) return;
      own([]);
      flushSync(() => clearSelection());
    },
    onClick: (ev: unknown) => {
      const [id] = rowIdsFromEvent(ds, ev as PointEvent);
      if (id) select([id]);
    },
  };

  return (
    <div ref={hover.ref} className="relative flex h-full flex-col">
      <div ref={plotBox} className="min-h-0 flex-1">
        <Plot
          data={fig.data}
          layout={layout}
          config={CONFIG}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          {...handlers}
          {...hover.handlers}
        />
      </div>
      {fig.note && <p className="px-2 pb-1 text-xs text-muted-foreground">{fig.note}</p>}
      {hover.card}
    </div>
  );
}
