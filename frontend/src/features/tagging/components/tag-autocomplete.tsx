"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useState } from "react";
import { useTags } from "../hooks/use-tags";

interface TagAutocompleteProps {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  /** "key" suggests distinct keys; "value" suggests distinct values. */
  field: "key" | "value";
  onEnter?: () => void;
  autoFocus?: boolean;
}

export function TagAutocomplete({
  value,
  onChange,
  placeholder,
  field,
  onEnter,
  autoFocus,
}: TagAutocompleteProps) {
  const [focused, setFocused] = useState(false);
  const { data: tags } = useTags({ q: value || undefined, limit: 25 });

  const suggestions = Array.from(
    new Set((tags ?? []).map((t) => (field === "key" ? t.key : (t.value ?? ""))).filter(Boolean)),
  )
    .filter((s) => s.toLowerCase() !== value.toLowerCase())
    .slice(0, 6);

  return (
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
      open={focused && value.length > 0 && suggestions.length > 0}
      onOpenChange={(o) => {
        if (!o) setFocused(false);
      }}
      onInputFocus={() => setFocused(true)}
      onInputKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onEnter?.();
        }
      }}
      autoFocus={autoFocus}
      placeholder={placeholder}
      inputClassName="h-8 text-sm"
    />
  );
}
