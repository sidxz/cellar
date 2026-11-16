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
import type { RefObject } from "react";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { panelTitle } from "./panels/panel-frame";
import type { WorkbenchTableHandle } from "./workbench-table";

/** Download a drawn panel at its on-screen size; PanelFrame tags its section with the id. */
function downloadPng(panelId: string, title: string) {
  const el = document.querySelector<HTMLElement>(`[data-panel-id="${panelId}"] .js-plotly-plot`);
  if (!el) return;
  getPlotlyGlobal()?.downloadImage?.(el, {
    format: "png",
    width: el.clientWidth || 1200,
    height: el.clientHeight || 600,
    filename: title.replace(/\W+/g, "-").replace(/^-|-$/g, ""),
  });
}

/** Export ▾: the table as CSV (visible columns, passing rows) and each shown plot as PNG. */
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
        <DropdownMenuItem onSelect={() => table.current?.exportCsv(`${ds.level}.csv`)}>
          Table as CSV
        </DropdownMenuItem>
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
