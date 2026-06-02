"use client";

import { useState } from "react";
import { Input } from "@/shared/components/ui/input";
import { useTags } from "../hooks/use-tags";

interface TagAutocompleteProps {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  /** "key" suggests distinct keys; "value" suggests distinct values. */
  field: "key" | "value";
  onEnter?: () => void;
}

export function TagAutocomplete({ value, onChange, placeholder, field, onEnter }: TagAutocompleteProps) {
  const [focused, setFocused] = useState(false);
  const { data: tags } = useTags({ q: value || undefined, limit: 25 });

  const suggestions = Array.from(
    new Set((tags ?? []).map((t) => (field === "key" ? t.key : (t.value ?? ""))).filter(Boolean)),
  )
    .filter((s) => s.toLowerCase() !== value.toLowerCase())
    .slice(0, 6);

  const showList = focused && value.length > 0 && suggestions.length > 0;

  return (
    <div className="relative">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onEnter?.();
          }
        }}
        placeholder={placeholder}
        className="h-8 text-sm"
      />
      {showList && (
        <ul className="absolute z-50 mt-1 max-h-40 w-full overflow-auto rounded-md border bg-popover py-1 text-sm shadow-md">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                className="flex w-full items-center px-2 py-1 text-left hover:bg-accent"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange(s);
                  setFocused(false);
                }}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
