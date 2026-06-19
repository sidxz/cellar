"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import type { FacetDimension, FacetGroup, FacetSelections } from "../lib/protocol-facets";

const FACET_VALUE_CAP = 8;

interface FacetSidebarProps {
  model: FacetGroup[];
  selections: FacetSelections;
  onToggle: (dim: FacetDimension, value: string) => void;
  onClear: () => void;
}

const hasAnySelection = (s: FacetSelections) => Object.values(s).some((set) => set && set.size > 0);

export function FacetSidebar({ model, selections, onToggle, onClear }: FacetSidebarProps) {
  return (
    <aside className="w-60 shrink-0 space-y-4 pr-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Filters</span>
        {hasAnySelection(selections) && (
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={onClear}>
            Clear
          </Button>
        )}
      </div>
      {model.map((group) => (
        <FacetGroupSection
          key={group.dimension}
          group={group}
          selected={selections[group.dimension]}
          onToggle={onToggle}
        />
      ))}
    </aside>
  );
}

function FacetGroupSection({
  group,
  selected,
  onToggle,
}: {
  group: FacetGroup;
  selected: Set<string> | undefined;
  onToggle: (dim: FacetDimension, value: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? group.values : group.values.slice(0, FACET_VALUE_CAP);
  return (
    <Collapsible defaultOpen className="space-y-1">
      <CollapsibleTrigger className="flex w-full items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
        {group.label}
        <ChevronDown className="h-3.5 w-3.5" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-0.5">
        {visible.map((v) => {
          const checked = selected?.has(v.value) ?? false;
          // Whole-row click target: a native <button role="checkbox"> is the ARIA-APG
          // checkbox pattern here (Enter/Space toggle, full-row affordance). A native
          // <input type=checkbox> can't host the indicator+label+count layout without a
          // wrapping <label>, which reintroduces the click-forwarding trap. The
          // resulting biome useSemanticElements warning is intentional.
          return (
            <button
              key={v.value}
              type="button"
              role="checkbox"
              aria-checked={checked}
              aria-label={v.label}
              onClick={() => onToggle(group.dimension, v.value)}
              className="flex w-full cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted"
            >
              <span
                aria-hidden
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border ${
                  checked ? "border-primary bg-primary text-primary-foreground" : "border-input"
                }`}
              >
                {checked && <Check className="h-3 w-3" />}
              </span>
              <span className="flex-1 truncate text-left">{v.label}</span>
              <span className="text-xs tabular-nums text-muted-foreground">{v.count}</span>
            </button>
          );
        })}
        {group.values.length > FACET_VALUE_CAP && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1 text-xs text-muted-foreground"
            onClick={() => setShowAll((s) => !s)}
          >
            {showAll ? "Show less" : `Show all (${group.values.length})`}
          </Button>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
