"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useState } from "react";
import { useDiscriminatorSuggestions } from "../hooks/use-protocol-name-preview";

interface DiscriminatorInputProps {
  value: string;
  onChange: (value: string) => void;
  /** The generated base name; suggestions already used on it come first. */
  base: string | null;
  placeholder?: string;
}

/** The one free part of a protocol name: a method or a fixed defining condition. */
export function DiscriminatorInput({
  value,
  onChange,
  base,
  placeholder = "e.g. resazurin, hypoxia (only when needed)",
}: DiscriminatorInputProps) {
  const [focused, setFocused] = useState(false);
  const suggestions = useDiscriminatorSuggestions(base, value)
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
      open={focused && suggestions.length > 0}
      onOpenChange={(o) => {
        if (!o) setFocused(false);
      }}
      onInputFocus={() => setFocused(true)}
      placeholder={placeholder}
      inputClassName="h-9"
    />
  );
}
