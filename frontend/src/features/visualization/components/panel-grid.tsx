"use client";

import { cn } from "@/shared/lib/utils";
import { numericValueColumn } from "../lib/default-panels";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { AddPlotMenu } from "./add-plot-menu";
import { ChartPanel } from "./panels/chart-panel";
import { type OnEditPanel, PanelFrame } from "./panels/panel-frame";
import { RGroupMatrixPanel } from "./panels/rgroup-matrix-panel";
import { ScatterPanel } from "./panels/scatter-panel";

/** The plots area: up to four panels in a 2×2 grid (a lone or odd last panel spans the
 * width), only the maximized one while one is, or an "Add plot" call to action. */
export function PanelGrid({ ds, onEdit }: { ds: Dataset; onEdit: OnEditPanel }) {
  const panels = useWorkbench((s) => s.panels);
  const maximized = useWorkbench((s) => s.maximized);
  const shown = maximized ? panels.filter((p) => p.id === maximized) : panels;

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      {!numericValueColumn(ds) && (
        <p className="rounded-md border border-dashed p-2 text-sm text-muted-foreground">
          No numeric fields to plot — showing well counts by category. The table still lists every
          value.
        </p>
      )}
      {shown.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          <p className="text-sm text-muted-foreground">No plots yet</p>
          <AddPlotMenu ds={ds} />
        </div>
      ) : (
        <div
          className={cn(
            "grid min-h-0 flex-1 auto-rows-fr gap-2",
            shown.length > 1 && "lg:grid-cols-2 lg:[&>:last-child:nth-child(odd)]:col-span-2",
          )}
        >
          {shown.map((p) => (
            <PanelFrame key={p.id} panel={p} ds={ds} onEdit={onEdit}>
              {p.type === "scatter" ? (
                <ScatterPanel panel={p} ds={ds} />
              ) : p.type === "rgroup-matrix" ? (
                <RGroupMatrixPanel panel={p} ds={ds} />
              ) : (
                <ChartPanel panel={p} ds={ds} />
              )}
            </PanelFrame>
          ))}
        </div>
      )}
    </div>
  );
}
