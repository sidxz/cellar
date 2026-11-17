"use client";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { getPlotlyGlobal } from "@/shared/lib/plotly";
import { ChevronDown, Download } from "lucide-react";
import { type RefObject, useMemo } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { actionSet } from "../lib/action-set";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { panelTitle } from "./panels/panel-frame";
import type { WorkbenchTableHandle } from "./workbench-table";

/** Download a drawn panel laid out at its on-screen size, at twice the pixels (sharp on
 * slides); PanelFrame tags its section with the id. */
function downloadPng(panelId: string, title: string) {
  const el = document.querySelector<HTMLElement>(`[data-panel-id="${panelId}"] .js-plotly-plot`);
  if (!el) return;
  getPlotlyGlobal()?.downloadImage?.(el, {
    format: "png",
    width: el.clientWidth || 1200,
    height: el.clientHeight || 600,
    scale: 2,
    filename: title.replace(/\W+/g, "-").replace(/^-|-$/g, ""),
  });
}

/** The CSV item: it acts on the same rows as Save (the selected passing rows, else every
 * passing row) and says which. Rendered only while the menu is open. */
function CsvItem({ ds, onExport }: { ds: Dataset; onExport: () => void }) {
  const selection = useWorkbench((s) => s.selection);
  const mask = usePassMask(ds);
  const { mode, rows } = useMemo(() => actionSet(ds, selection, mask), [ds, selection, mask]);
  const n = rows.length;
  const what = `${n.toLocaleString()}${mode === "selected" ? " selected" : ""} ${n === 1 ? "row" : "rows"}`;
  return <DropdownMenuItem onSelect={onExport}>Export {what} as CSV</DropdownMenuItem>;
}

/** Export ▾: the table as CSV (visible columns) and each shown plot as PNG. */
export function ExportMenu({
  ds,
  table,
}: {
  ds: Dataset;
  table: RefObject<WorkbenchTableHandle | null>;
}) {
  const panels = useWorkbench((s) => s.panels);
  const maximized = useWorkbench((s) => s.maximized);
  // Only drawn panels can be captured.
  const shown = maximized ? panels.filter((p) => p.id === maximized) : panels;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" className="h-8">
          <Download className="h-4 w-4" />
          Export
          <ChevronDown className="h-3.5 w-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <CsvItem ds={ds} onExport={() => table.current?.exportCsv(`${ds.level}.csv`)} />
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Plot as PNG</DropdownMenuLabel>
        {shown.length === 0 && <DropdownMenuItem disabled>No plots open</DropdownMenuItem>}
        {shown.map((p) => {
          const title = panelTitle(ds, p);
          return (
            <DropdownMenuItem key={p.id} onSelect={() => downloadPng(p.id, title)}>
              <span className="truncate">{title}</span>
            </DropdownMenuItem>
          );
        })}
        <p className="px-2 py-1.5 text-xs text-muted-foreground">
          PNG only: SVG of WebGL plots embeds a raster image.
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
