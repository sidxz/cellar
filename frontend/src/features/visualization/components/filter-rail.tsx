"use client";

import { Button } from "@/shared/components/ui/button";
import { FilterX } from "lucide-react";
import { type ReactNode, memo, useMemo } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { filterSummary, isFilterActive } from "../lib/filters";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";
import { AddFilterCombobox } from "./filters/add-filter-combobox";
import { CategoryFilterCard } from "./filters/category-filter-card";
import { FilterCard } from "./filters/filter-card";
import { RangeFilterCard } from "./filters/range-filter-card";
import { SubstructureFilterCard } from "./filters/substructure-filter-card";

/** The filter rail: "Filters (n active)" + Reset all (one undo step), the fixed-bins note,
 * the field search, then one card per filter. Memoized: it redraws only on filter or
 * dataset changes, not on selection or panel edits. */
export const FilterRail = memo(function FilterRail({ ds }: { ds: Dataset }) {
  const filters = useWorkbench((s) => s.filters);
  const setFilters = useWorkbench((s) => s.setFilters);
  const active = useMemo(
    () => new Set(filters.filter((f) => isFilterActive(ds, f)).map((f) => f.id)),
    [ds, filters],
  );

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
        <h4 className="text-sm font-semibold">
          Filters <span className="font-normal text-muted-foreground">({active.size} active)</span>
        </h4>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto h-7"
          disabled={filters.length === 0}
          onClick={() => setFilters([])}
        >
          Reset all
        </Button>
      </div>
      <div className="space-y-2 px-3 pb-3">
        <p className="text-xs text-muted-foreground">
          Histograms use fixed bins and show rows that pass the other filters.
        </p>
        <AddFilterCombobox ds={ds} />
        {filters.map((f) => {
          const on = active.has(f.id);
          if (f.kind === "range")
            return <RangeFilterCard key={f.id} ds={ds} filter={f} active={on} />;
          if (f.kind === "category") {
            return <CategoryFilterCard key={f.id} ds={ds} filter={f} active={on} />;
          }
          if (f.kind === "substructure") {
            return <SubstructureFilterCard key={f.id} ds={ds} filter={f} active={on} />;
          }
          return <FilterCard key={f.id} ds={ds} filter={f} active={on} />;
        })}
      </div>
    </div>
  );
});

/** Shows ``children`` while any row passes; otherwise "No rows match", the active filters
 * and a Clear filters button (one undo step). */
export function NoRowsMatch({ ds, children }: { ds: Dataset; children: ReactNode }) {
  const mask = usePassMask(ds);
  const filters = useWorkbench((s) => s.filters);
  const setFilters = useWorkbench((s) => s.setFilters);
  const none = useMemo(() => ds.row_count > 0 && !mask.includes(1), [ds, mask]);
  if (!none) return children;
  const listed = filters.filter((f) => isFilterActive(ds, f)).map((f) => filterSummary(ds, f));
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
      <FilterX className="h-8 w-8 text-muted-foreground/50" />
      <h3 className="font-semibold">No rows match</h3>
      <ul className="text-sm text-muted-foreground">
        {listed.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
      <Button size="sm" onClick={() => setFilters([])}>
        Clear filters
      </Button>
    </div>
  );
}
