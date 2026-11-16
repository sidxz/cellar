"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { useId, useMemo, useState } from "react";
import { categoryLabel } from "../../lib/dataset";
import { type Filter, categoryValues, computePassMask } from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FilterCard } from "./filter-card";

type CategoryFilter = Extract<Filter, { kind: "category" }>;

/** Past this many values the list gets a search box and shows at most SHOWN of them. */
const SEARCH_FROM = 10;
const SHOWN = 100;
const MISSING = "\u0000missing";

/** A checklist of a category column's values, each with its count among the rows the
 * other filters keep; "(none)" stands for rows without a value. One undo entry per click. */
export function CategoryFilterCard({
  ds,
  filter,
  active,
}: {
  ds: Dataset;
  filter: CategoryFilter;
  active: boolean;
}) {
  const filters = useWorkbench((s) => s.filters);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const [query, setQuery] = useState("");
  const id = useId();

  const all = useMemo(() => categoryValues(ds, filter.key), [ds, filter.key]);
  const counts = useMemo(() => {
    const others = computePassMask(ds, filters, filter.id);
    const col = ds.values[filter.key] ?? [];
    const out = new Map<string, number>();
    for (let i = 0; i < others.length; i++) {
      if (!others[i]) continue;
      const v = col[i];
      const k = v === null || v === undefined ? MISSING : String(v);
      out.set(k, (out.get(k) ?? 0) + 1);
    }
    return out;
  }, [ds, filters, filter.id, filter.key]);

  const kept = new Set(filter.values);
  const items = [
    ...all.values.map((v) => ({ value: v, label: categoryLabel(filter.key, v), on: kept.has(v) })),
    ...(all.hasMissing
      ? [{ value: MISSING, label: categoryLabel(filter.key, null), on: filter.includeMissing }]
      : []),
  ];
  const q = query.trim().toLowerCase();
  const matching = q ? items.filter((it) => it.label.toLowerCase().includes(q)) : items;

  const toggle = (value: string, on: boolean) => {
    if (value === MISSING) {
      upsertFilter({ ...filter, includeMissing: on });
      return;
    }
    const next = new Set(filter.values);
    if (on) next.add(value);
    else next.delete(value);
    upsertFilter({ ...filter, values: [...next] });
  };
  const setAll = (on: boolean) =>
    upsertFilter({ ...filter, values: on ? all.values : [], includeMissing: on });

  return (
    <FilterCard ds={ds} filter={filter} active={active}>
      <div className="flex items-center gap-1">
        {items.length > SEARCH_FROM && (
          <Input
            aria-label="Search values"
            placeholder="Search values…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-7 min-w-0 flex-1 px-2 text-xs"
          />
        )}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto h-6 px-1.5 text-xs"
          onClick={() => setAll(true)}
        >
          All
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-xs"
          onClick={() => setAll(false)}
        >
          None
        </Button>
      </div>
      <ul className="max-h-60 space-y-0.5 overflow-auto">
        {matching.slice(0, SHOWN).map((it, k) => (
          <li key={it.value} className="flex items-center gap-2 text-xs">
            <Checkbox
              id={`${id}-${k}`}
              checked={it.on}
              onCheckedChange={(on) => toggle(it.value, on === true)}
            />
            <label htmlFor={`${id}-${k}`} className="flex min-w-0 flex-1 gap-2">
              <span className="min-w-0 truncate">{it.label}</span>
              <span className="ml-auto tabular-nums text-muted-foreground">
                {(counts.get(it.value) ?? 0).toLocaleString()}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {matching.length > SHOWN && (
        <p className="text-xs text-muted-foreground">
          Showing {SHOWN} of {matching.length.toLocaleString()} — search to narrow.
        </p>
      )}
    </FilterCard>
  );
}
