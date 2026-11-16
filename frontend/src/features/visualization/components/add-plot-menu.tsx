"use client";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import {
  ChartCandlestick,
  ChartColumn,
  ChartColumnStacked,
  ChartScatter,
  Plus,
} from "lucide-react";
import { numericValueColumn, panelDefaults } from "../lib/default-panels";
import { useWorkbench } from "../store/workbench-context";
import { MAX_PANELS, type PanelType } from "../store/workbench-store";
import type { Dataset } from "../types";

const TYPES = [
  { type: "scatter", label: "Scatter", icon: ChartScatter, numeric: true },
  { type: "histogram", label: "Histogram", icon: ChartColumnStacked, numeric: true },
  { type: "bar", label: "Bar", icon: ChartColumn, numeric: false },
  { type: "box", label: "Box", icon: ChartCandlestick, numeric: true },
] satisfies { type: PanelType; label: string; icon: typeof Plus; numeric: boolean }[];

/** "+ Add plot (n/4)": a type menu that adds a panel with sensible fields; disabled, with
 * the reason on hover, once four plots are open. */
export function AddPlotMenu({ ds }: { ds: Dataset }) {
  const count = useWorkbench((s) => s.panels.length);
  const addPanel = useWorkbench((s) => s.addPanel);
  const setMaximized = useWorkbench((s) => s.setMaximized);
  const full = count >= MAX_PANELS;
  const hasNumeric = Boolean(numericValueColumn(ds));

  const add = (type: PanelType) => {
    // A maximized plot would hide the new one.
    if (addPanel(type, panelDefaults(ds, type))) setMaximized(null);
  };

  return (
    // A disabled button shows no tooltip of its own; the wrapper carries the reason.
    <span title={full ? "Up to 4 plots — close one to add another" : undefined}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" className="h-8" disabled={full}>
            <Plus className="h-4 w-4" />
            Add plot ({count}/{MAX_PANELS})
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {TYPES.map(({ type, label, icon: Icon, numeric }) => (
            <DropdownMenuItem
              key={type}
              disabled={numeric && !hasNumeric}
              onSelect={() => add(type)}
            >
              <Icon className="h-4 w-4" />
              {label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  );
}
