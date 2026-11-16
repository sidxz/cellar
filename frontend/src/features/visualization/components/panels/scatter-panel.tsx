"use client";

import {
  type PlotlySelectionEvent,
  hasSelectionGeometry,
} from "@/features/sar-analysis/lib/lasso-math";
import { Plot } from "@/shared/lib/plotly";
import { useTheme } from "next-themes";
import { useMemo, useRef } from "react";
import { flushSync } from "react-dom";
import { usePassMask } from "../../hooks/use-pass-mask";
import { type PointEvent, buildScatterFigure, rowIdsFromEvent } from "../../lib/traces/scatter";
import { useWorkbench } from "../../store/workbench-context";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";

const CONFIG = { displaylogo: false };

const sameSet = (ids: string[], set: ReadonlySet<string>) =>
  ids.length === set.size && ids.every((id) => set.has(id));

/** Counts selection clears, so the plot drops its own lasso outline when the selection
 * is cleared from elsewhere (strip, table) — the count is the plot's selectionrevision. */
function useClearCount(selection: ReadonlySet<string>): number {
  const ref = useRef({ had: false, clears: 0 });
  if (ref.current.had && selection.size === 0) ref.current.clears += 1;
  ref.current.had = selection.size > 0;
  return ref.current.clears;
}

export function ScatterPanel({ panel, ds }: { panel: PanelConfig; ds: Dataset }) {
  const mask = usePassMask(ds);
  const selection = useWorkbench((s) => s.selection);
  const setSelection = useWorkbench((s) => s.setSelection);
  const clearSelection = useWorkbench((s) => s.clearSelection);
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const clears = useClearCount(selection);

  const fig = useMemo(
    () => buildScatterFigure(ds, panel, mask, selection, dark),
    [ds, panel, mask, selection, dark],
  );
  // Constant uirevision (in the figure) keeps zoom and the lasso across redraws.
  const layout = useMemo(
    () => ({ ...fig.layout, selectionrevision: `${panel.id}:${clears}` }),
    [fig.layout, panel.id, clears],
  );

  // Plotly fires these from its own emitter, outside React's batching: flushSync makes
  // the store change render now. Same pattern as the SAR cluster map.
  const select = (ids: string[]) => {
    if (!sameSet(ids, selection)) flushSync(() => setSelection(ids));
  };
  const handlers = {
    onSelected: (ev: unknown) => {
      // Redraws re-emit plotly_selected without geometry; only a real lasso/box has it.
      if (!hasSelectionGeometry(ev as PlotlySelectionEvent)) return;
      select(rowIdsFromEvent(ds, ev as PointEvent));
    },
    onDeselect: () => {
      if (selection.size > 0) flushSync(() => clearSelection());
    },
    onClick: (ev: unknown) => {
      const [id] = rowIdsFromEvent(ds, ev as PointEvent);
      if (id) select([id]);
    },
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
        <Plot
          data={fig.data}
          layout={layout}
          config={CONFIG}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          {...handlers}
        />
      </div>
      {fig.note && <p className="px-2 pb-1 text-xs text-muted-foreground">{fig.note}</p>}
    </div>
  );
}
