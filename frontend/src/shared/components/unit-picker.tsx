"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { type UnitSuggestion, useUnits } from "@/shared/hooks/use-units";
import { useState } from "react";

const fold = (s: string) => s.replace(/[uμ]/g, "µ").toLowerCase();

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
        <span className="flex w-full justify-between">
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
