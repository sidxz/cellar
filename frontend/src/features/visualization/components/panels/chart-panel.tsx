"use client";

import { Plot } from "@/shared/lib/plotly";
import { useTheme } from "next-themes";
import { useMemo } from "react";
import { usePassMask } from "../../hooks/use-pass-mask";
import { buildOverlays, mergeOverlays } from "../../lib/overlays/build";
import { buildBarFigure } from "../../lib/traces/bar";
import { buildBoxFigure } from "../../lib/traces/box";
import { buildHistogramFigure } from "../../lib/traces/histogram";
import type { PanelConfig, PanelType } from "../../store/workbench-store";
import type { Dataset } from "../../types";

const CONFIG = { displaylogo: false };
const BUILDERS = { histogram: buildHistogramFigure, bar: buildBarFigure, box: buildBoxFigure };

/** A histogram, bar or box panel: a figure of the passing rows (no selection from these
 * yet — selection comes from scatters and the table), with its "rows lack" note. */
export function ChartPanel({ panel, ds }: { panel: PanelConfig; ds: Dataset }) {
  const mask = usePassMask(ds);
  const dark = useTheme().resolvedTheme === "dark";
  const fig = useMemo(() => {
    const f = BUILDERS[panel.type as Exclude<PanelType, "scatter">](ds, panel, mask, dark);
    return f.facets ? mergeOverlays(f, buildOverlays(ds, panel, mask, f.facets)) : f;
  }, [ds, panel, mask, dark]);
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
        <Plot
          data={fig.data}
          layout={fig.layout}
          config={CONFIG}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
      {fig.note && <p className="px-2 pb-1 text-xs text-muted-foreground">{fig.note}</p>}
    </div>
  );
}
