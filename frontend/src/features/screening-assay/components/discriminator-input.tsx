"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { Button } from "@/shared/components/ui/button";
import { useState } from "react";
import { useDiscriminatorSuggestions } from "../hooks/use-protocol-name-preview";
import { type ConditionDraft, fixedConditionChips } from "../lib/test-concentration";

interface DiscriminatorInputProps {
  value: string;
  onChange: (value: string) => void;
  /** The generated base name; suggestions already used on it come first. */
  base: string | null;
  placeholder?: string;
  /** Forwarded to the input so a label can target it. */
  id?: string;
  /** This protocol's conditions; each fixed value is offered as a one-click chip. */
  conditions?: ConditionDraft[];
}

/** The one free part of a protocol name: a method or a fixed defining condition. */
export function DiscriminatorInput({
  value,
  onChange,
  base,
  id,
  conditions = [],
  placeholder = "e.g. resazurin, hypoxia (only when needed)",
}: DiscriminatorInputProps) {
  const [focused, setFocused] = useState(false);
  const chips = fixedConditionChips(conditions).filter(
    (c) => c.toLowerCase() !== value.trim().toLowerCase(),
  );
  // A chip already shows its value, so the list does not repeat it.
  const suggestions = useDiscriminatorSuggestions(base, value)
    .filter(
      (s) =>
        s.toLowerCase() !== value.toLowerCase() &&
        !chips.some((c) => c.toLowerCase() === s.toLowerCase()),
    )
    .slice(0, 6);
  return (
    <div className="grid gap-1.5">
      <SearchCombobox<string>
        searchValue={value}
        onSearchChange={onChange}
        items={suggestions}
        getItemKey={(s) => s}
        renderItem={(s) => s}
        onSelect={(s) => {
          onChange(s);
          setFocused(false);
        }}
        open={focused && suggestions.length > 0}
        onOpenChange={(o) => {
          if (!o) setFocused(false);
        }}
        onInputFocus={() => setFocused(true)}
        placeholder={placeholder}
        id={id}
        inputClassName="h-9"
      />
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Fixed here:</span>
          {chips.map((c) => (
            <Button
              key={c}
              type="button"
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => onChange(c)}
            >
              {c}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
