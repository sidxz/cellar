"use client";

import { Button } from "@/shared/components/ui/button";
import { Maximize2, Minimize2, Pencil, X } from "lucide-react";
import type { ReactNode } from "react";
import { column } from "../../lib/dataset";
import { fieldLabel } from "../../lib/traces/common";
import { useWorkbench } from "../../store/workbench-context";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";

/** A panel setting the plot editor can open at. */
export type EditField = "x" | "y" | "category" | "colorBy" | "shapeBy" | "splitBy";
export type OnEditPanel = (panelId: string, focusField?: EditField) => void;

const labelOf = (ds: Dataset, key?: string) => (key ? fieldLabel(ds, key) : "—");

export function panelTitle(ds: Dataset, p: PanelConfig): string {
  const l = (key?: string) => labelOf(ds, key);
  switch (p.type) {
    case "scatter":
      return `${l(p.y)} by ${l(p.x)}`;
    case "histogram":
      return `Distribution of ${l(p.x)}`;
    case "box":
      return `${l(p.y)} by ${l(p.category)}`;
    case "bar":
      return !p.agg || p.agg === "count"
        ? `Count by ${l(p.category)}`
        : `${p.agg === "mean" ? "Mean" : "Median"} ${l(p.y)} by ${l(p.category)}`;
    case "rgroup-matrix": {
      const what = p.y ? `${p.agg === "mean" ? "Mean" : "Median"} ${l(p.y)}` : "Compounds";
      const set = p.x ? column(ds, p.x)?.group : undefined;
      return `${what} by ${l(p.category)} × ${l(p.x)}${set ? ` (${set})` : ""}`;
    }
  }
}

/** The header chips: one per field the plot draws with, each a shortcut into the editor.
 * Settings a type ignores (kept so switching back restores them) get no chip. */
function chips(ds: Dataset, p: PanelConfig): { field: EditField; name: string; text: string }[] {
  const a = p.appearance;
  const scatter = p.type === "scatter";
  const text = (key: string, log?: boolean) => `${labelOf(ds, key)}${log ? " (log)" : ""}`;
  const y = p.type === "box" || scatter || (p.type === "bar" && (p.agg ?? "count") !== "count");
  // Histograms stack by a category color only.
  const color =
    scatter || (p.type === "histogram" && a.colorBy && column(ds, a.colorBy)?.kind !== "number");
  const shape = scatter ? a.shapeBy : undefined;
  const out: { field: EditField; name: string; text: string }[] = [];
  if (p.type === "rgroup-matrix") {
    if (p.category) out.push({ field: "category", name: "Rows", text: text(p.category) });
    if (p.x) out.push({ field: "x", name: "Columns", text: text(p.x) });
    if (p.y) out.push({ field: "y", name: "Value", text: text(p.y) });
    return out;
  }
  if (y && p.y) out.push({ field: "y", name: "Y", text: text(p.y, p.logY) });
  if (p.x && p.type !== "bar" && p.type !== "box") {
    out.push({ field: "x", name: "X", text: text(p.x, scatter && p.logX) });
  }
  if (p.category && (p.type === "bar" || p.type === "box")) {
    out.push({ field: "category", name: "Group", text: text(p.category) });
  }
  if (scatter && a.splitBy) out.push({ field: "splitBy", name: "Split", text: text(a.splitBy) });
  if (color && a.colorBy) {
    const name = shape === a.colorBy ? "Color + shape" : scatter ? "Color" : "Stack";
    out.push({ field: "colorBy", name, text: text(a.colorBy) });
  }
  if (shape && shape !== a.colorBy)
    out.push({ field: "shapeBy", name: "Shape", text: text(shape) });
  return out;
}

/** A plot's frame: title, clickable field chips, a labeled Edit plot button,
 * maximize/restore and close. */
export function PanelFrame({
  panel,
  ds,
  onEdit,
  children,
}: {
  panel: PanelConfig;
  ds: Dataset;
  onEdit: OnEditPanel;
  children: ReactNode;
}) {
  const maximized = useWorkbench((s) => s.maximized === panel.id);
  const setMaximized = useWorkbench((s) => s.setMaximized);
  const removePanel = useWorkbench((s) => s.removePanel);
  const title = panelTitle(ds, panel);
  return (
    <section
      aria-label={title}
      data-panel-id={panel.id}
      className="flex h-full min-h-[240px] min-w-0 flex-col rounded-md border bg-card"
    >
      <header className="flex flex-wrap items-center gap-1.5 border-b px-2 py-1">
        <h3 className="mr-1 truncate text-sm font-medium">{title}</h3>
        {chips(ds, panel).map((c) => (
          <button
            key={c.field}
            type="button"
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:border-primary hover:text-primary"
            onClick={() => onEdit(panel.id, c.field)}
          >
            <span className="text-muted-foreground">{c.name}</span> {c.text}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-0.5">
          <Button size="sm" variant="outline" className="h-7" onClick={() => onEdit(panel.id)}>
            <Pencil className="h-3.5 w-3.5" />
            Edit plot
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={maximized ? "Restore plot" : "Maximize plot"}
            onClick={() => setMaximized(maximized ? null : panel.id)}
          >
            {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label="Close plot"
            onClick={() => removePanel(panel.id)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </header>
      <div className="relative min-h-0 flex-1 overflow-hidden">{children}</div>
    </section>
  );
}
