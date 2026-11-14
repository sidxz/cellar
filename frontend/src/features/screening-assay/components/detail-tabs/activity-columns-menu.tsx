"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Label } from "@/shared/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Columns3 } from "lucide-react";
import { useCallback, useState } from "react";
import type { CatalogColumn, ColumnChoices } from "../../lib/activity-columns";

const EMPTY: ColumnChoices = { shown: [], hidden: [] };

function read(key: string): ColumnChoices {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? (JSON.parse(raw) as Partial<ColumnChoices>) : null;
    return {
      shown: Array.isArray(parsed?.shown) ? parsed.shown : [],
      hidden: Array.isArray(parsed?.hidden) ? parsed.hidden : [],
    };
  } catch {
    return EMPTY;
  }
}

/** The user's column choices for one protocol's Activity grid, kept per browser. */
export function useColumnChoices(protocolId: string) {
  const key = `cellar.activity.columns.${protocolId}`;
  const [choices, setChoices] = useState<ColumnChoices>(() => read(key));
  const save = useCallback(
    (next: ColumnChoices) => {
      setChoices(next);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Storage unavailable: the choice holds for this visit only.
      }
    },
    [key],
  );
  const toggle = useCallback(
    (column: CatalogColumn, show: boolean) => {
      const without = (ids: readonly string[]) => ids.filter((id) => id !== column.colId);
      save({
        // Only a departure from the default is stored.
        shown:
          show && !column.defaultVisible
            ? [...without(choices.shown), column.colId]
            : without(choices.shown),
        hidden:
          !show && column.defaultVisible
            ? [...without(choices.hidden), column.colId]
            : without(choices.hidden),
      });
    },
    [choices, save],
  );
  return { choices, toggle, reset: () => save(EMPTY) };
}

/** Show or hide any result column; columns with no results say so. */
export function ActivityColumnsMenu({
  catalog,
  visible,
  onToggle,
  onReset,
}: {
  catalog: readonly CatalogColumn[];
  visible: ReadonlySet<string>;
  onToggle: (column: CatalogColumn, show: boolean) => void;
  onReset: () => void;
}) {
  const groups = new Map<string, CatalogColumn[]>();
  for (const c of catalog) {
    const g = c.group ?? "Results";
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 className="mr-1.5 h-3.5 w-3.5" />
          Columns
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[60vh] w-80 overflow-y-auto">
        <div className="space-y-3">
          {[...groups].map(([group, cols]) => (
            <div key={group} className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">{group}</p>
              {cols.map((c) => {
                const id = `col-${c.colId}`;
                return (
                  <div key={c.colId} className="flex items-center gap-2">
                    <Checkbox
                      id={id}
                      checked={visible.has(c.colId)}
                      onCheckedChange={(v) => onToggle(c, v === true)}
                    />
                    <Label htmlFor={id} className="font-normal" title={c.readout}>
                      {c.label}
                    </Label>
                    {c.empty && <span className="text-xs text-muted-foreground">no results</span>}
                  </div>
                );
              })}
            </div>
          ))}
          <Button variant="ghost" size="sm" className="w-full" onClick={onReset}>
            Reset to defaults
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
