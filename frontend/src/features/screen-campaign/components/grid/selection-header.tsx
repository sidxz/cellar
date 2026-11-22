"use client";

import type { IHeaderParams } from "ag-grid-community";
import { ChevronDown } from "lucide-react";
import { useEffect, useReducer } from "react";

import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";

/** The # column's header for editors: a box that ticks every visible row (or clears the
 *  ticks), and a menu to tick every visible row, every row in the table, or none. "Visible" is
 *  what the filters let through; ticking all in the table reaches the rows they hide too. */
export function SelectionHeader({ api }: Pick<IHeaderParams, "api">) {
  // AG Grid owns the selection; redraw whenever it or the visible rows change.
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    api.addEventListener("selectionChanged", redraw);
    api.addEventListener("modelUpdated", redraw);
    return () => {
      api.removeEventListener("selectionChanged", redraw);
      api.removeEventListener("modelUpdated", redraw);
    };
  }, [api]);

  const selected = api.getSelectedNodes().length;
  const visible = api.getDisplayedRowCount();
  let total = 0;
  api.forEachNode(() => {
    total += 1;
  });
  let visibleSelected = 0;
  api.forEachNodeAfterFilter((n) => {
    if (n.isSelected()) visibleSelected += 1;
  });
  const checked =
    selected === 0
      ? false
      : visibleSelected === visible && selected === visible
        ? true
        : "indeterminate";
  const selectVisible = () => {
    api.deselectAll();
    api.selectAll("filtered");
  };

  return (
    // On the column labels' row, as the other spanning headers sit.
    <span className="flex items-center gap-0.5 self-end pb-2">
      <Checkbox
        checked={checked}
        aria-label={selected > 0 ? "Clear selection" : `Select all ${visible} visible rows`}
        onCheckedChange={() => (selected > 0 ? api.deselectAll() : selectVisible())}
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label="Selection options"
            className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className="size-3" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={selectVisible}>Select all {visible} visible</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => api.selectAll("all")}>
            Select all {total} in the table
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={selected === 0} onSelect={() => api.deselectAll()}>
            Clear selection
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <span className="ml-1" title="Row number">
        #
      </span>
    </span>
  );
}
