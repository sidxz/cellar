"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { column } from "../../lib/dataset";
import {
  type Filter,
  filterCondition,
  filterSummary,
  substructureSummary,
} from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";

/** A rail card: a header that collapses the card to its summary (highlighted while the
 * filter leaves rows out) and removes the filter, over the card's controls. */
export function FilterCard({
  ds,
  filter,
  active,
  children,
}: {
  ds: Dataset;
  filter: Filter;
  active: boolean;
  children?: ReactNode;
}) {
  const removeFilter = useWorkbench((s) => s.removeFilter);
  const [open, setOpen] = useState(true);
  const label =
    filter.kind === "rows"
      ? "Selection"
      : filter.kind === "substructure"
        ? substructureSummary(filter)
        : (column(ds, filter.key)?.label ?? filter.key);
  const { condition, summary } = useMemo(
    () => ({ condition: filterCondition(ds, filter), summary: filterSummary(ds, filter) }),
    [ds, filter],
  );
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <fieldset aria-label={label} className="min-w-0 rounded-md border bg-card">
      <div className="flex items-center gap-1 pr-1">
        <button
          type="button"
          aria-expanded={children ? open : undefined}
          aria-label={summary}
          data-active={active}
          className="flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left text-sm"
          onClick={() => setOpen((o) => !o)}
        >
          <Icon
            className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground", !children && "invisible")}
          />
          <span className="truncate font-medium">{label}</span>
          <span
            className={cn(
              "ml-auto shrink-0 text-xs",
              active ? "font-semibold text-primary" : "text-muted-foreground",
            )}
          >
            {condition}
          </span>
        </button>
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 shrink-0"
          aria-label={`Remove filter ${label}`}
          onClick={() => removeFilter(filter.id)}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      {open && children && <div className="space-y-2 px-2 pb-2">{children}</div>}
    </fieldset>
  );
}
