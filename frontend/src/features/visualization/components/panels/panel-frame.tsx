"use client";

import { Button } from "@/shared/components/ui/button";
import { Maximize2, Minimize2, Pencil, X } from "lucide-react";
import type { ReactNode } from "react";
import { column } from "../../lib/dataset";
import { useWorkbench } from "../../store/workbench-context";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";

/** A panel setting the plot editor can open at. */
export type EditField = "x" | "y" | "category" | "colorBy" | "shapeBy" | "splitBy";
export type OnEditPanel = (panelId: string, focusField?: EditField) => void;

const labelOf = (ds: Dataset, key?: string) => (key ? (column(ds, key)?.label ?? key) : "—");

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
  }
}

/** The header chips: one per configured field, each a shortcut into the editor. */
function chips(ds: Dataset, p: PanelConfig): { field: EditField; name: string; text: string }[] {
  const a = p.appearance;
  const text = (key: string, log?: boolean) => `${labelOf(ds, key)}${log ? " (log)" : ""}`;
  const out: { field: EditField; name: string; text: string }[] = [];
  if (p.y) out.push({ field: "y", name: "Y", text: text(p.y, p.logY) });
  if (p.x) out.push({ field: "x", name: "X", text: text(p.x, p.logX) });
  if (p.category) out.push({ field: "category", name: "Group", text: text(p.category) });
  if (a.splitBy) out.push({ field: "splitBy", name: "Split", text: text(a.splitBy) });
  if (a.colorBy) {
    const name = a.shapeBy === a.colorBy ? "Color + shape" : "Color";
    out.push({ field: "colorBy", name, text: text(a.colorBy) });
  }
  if (a.shapeBy && a.shapeBy !== a.colorBy) {
    out.push({ field: "shapeBy", name: "Shape", text: text(a.shapeBy) });
  }
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
      <div className="relative min-h-0 flex-1">{children}</div>
    </section>
  );
}
