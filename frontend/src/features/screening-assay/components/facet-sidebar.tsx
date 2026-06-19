"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
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
          return (
            // biome-ignore lint/a11y/noLabelWithoutControl: Checkbox is the control; it receives aria-label for accessible name
            // biome-ignore lint/a11y/useKeyWithClickEvents: <label> wrapping a <button role="checkbox"> is keyboard-accessible via Enter/Space on the button itself
            <label
              key={v.value}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted"
              onClick={() => onToggle(group.dimension, v.value)}
            >
              <Checkbox checked={checked} aria-label={v.label} tabIndex={-1} />
              <span className="flex-1 truncate">{v.label}</span>
              <span className="text-xs tabular-nums text-muted-foreground">{v.count}</span>
            </label>
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
