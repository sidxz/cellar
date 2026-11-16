"use client";

import { Button } from "@/shared/components/ui/button";
import { useMemo } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { actionSet } from "../lib/action-set";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

const fmt = (n: number) => n.toLocaleString();

/** Above the table while something is selected: how many selected rows the filters
 * show and hide, with Clear and Filter to selection. */
export function SelectionStrip({ ds }: { ds: Dataset }) {
  const selection = useWorkbench((s) => s.selection);
  const clearSelection = useWorkbench((s) => s.clearSelection);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const mask = usePassMask(ds);
  const set = useMemo(
    () => (selection.size > 0 ? actionSet(ds, selection, mask) : null),
    [ds, selection, mask],
  );
  if (!set) return null;

  const visible = set.rows.length;
  const total = visible + set.hiddenSelected;
  const filterToSelection = () => {
    upsertFilter({ id: "selection", kind: "rows", rowIds: [...selection] });
    clearSelection();
  };
  return (
    <div className="flex shrink-0 items-center gap-2 border-b bg-primary/5 px-3 py-1 text-sm">
      <output>
        <b>{fmt(total)}</b> {total === 1 ? "well" : "wells"} selected · <b>{fmt(visible)}</b>{" "}
        visible · <b>{fmt(set.hiddenSelected)}</b> hidden by filters
      </output>
      <Button size="sm" variant="outline" className="ml-auto h-7" onClick={clearSelection}>
        Clear
      </Button>
      <Button size="sm" variant="outline" className="h-7" onClick={filterToSelection}>
        Filter to selection
      </Button>
    </div>
  );
}
