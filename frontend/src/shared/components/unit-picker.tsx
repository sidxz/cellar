"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { type UnitSuggestion, useUnits } from "@/shared/hooks/use-units";
import { useState } from "react";

// Lowercase first, so a capital U (RLU, AU, CFU) folds to µ like the query's u does.
const fold = (s: string) => s.toLowerCase().replace(/[uμ]/g, "µ");

/** Spelling-tolerant match: "uM" finds µM, "ug/ml" finds µg/mL. The backend stores the canonical spelling. */
export function unitMatches(unit: string, query: string): boolean {
  return fold(unit).includes(fold(query.trim()));
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

export function UnitPicker({ value, onChange, placeholder = "Unit" }: Props) {
  const [open, setOpen] = useState(false);
  const { data } = useUnits();
  const items = (data ?? [])
    .filter((u) => !value || (unitMatches(u.unit, value) && u.unit !== value))
    .slice(0, 8);
  return (
    <SearchCombobox<UnitSuggestion>
      searchValue={value}
      onSearchChange={onChange}
      items={items}
      getItemKey={(u) => u.unit}
      renderItem={(u) => (
        // The popover is as wide as its rows, so the gap is what keeps "µM" and its group apart.
        <span className="flex w-full justify-between gap-4">
          <span>{u.unit}</span>
          <span className="text-xs text-muted-foreground">{u.group}</span>
        </span>
      )}
      onSelect={(u) => {
        onChange(u.unit);
        setOpen(false);
      }}
      open={open && items.length > 0}
      onOpenChange={setOpen}
      onInputFocus={() => setOpen(true)}
      placeholder={placeholder}
      inputClassName="h-9"
    />
  );
}
