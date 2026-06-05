"use client";

import { Plus } from "lucide-react";
import { defaultScaffoldCriterion } from "../../lib/search-query-config";
import type { ScaffoldCriterion } from "../../types";
import { ScaffoldCriterionRow } from "../criterion-rows/scaffold-rows";

interface ScaffoldSectionProps {
  criteria: ScaffoldCriterion[];
  onChange: (criteria: ScaffoldCriterion[]) => void;
}

export function ScaffoldSection({ criteria, onChange }: ScaffoldSectionProps) {
  function addCriterion() {
    onChange([...criteria, defaultScaffoldCriterion()]);
  }

  function updateCriterion(index: number, updated: ScaffoldCriterion) {
    onChange(criteria.map((c, i) => (i === index ? updated : c)));
  }

  function removeCriterion(index: number) {
    onChange(criteria.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Scaffold
        </span>
        <button
          type="button"
          onClick={addCriterion}
          className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add
        </button>
      </div>

      {criteria.length === 0 && (
        <p className="text-sm italic text-muted-foreground/50">No scaffold filters.</p>
      )}

      <div className="space-y-2">
        {criteria.map((c, i) => (
          <ScaffoldCriterionRow
            key={`scaffold-${i}`}
            criterion={c}
            onChange={(updated) => updateCriterion(i, updated)}
            onRemove={() => removeCriterion(i)}
          />
        ))}
      </div>

      {criteria.some((c) => c.mode === "exact_match") && (
        <p className="text-xs text-muted-foreground/70">
          Compared to the canonical Bemis-Murcko scaffold. Decorated molecules are stripped to their
          scaffold before comparing.
        </p>
      )}
    </div>
  );
}
