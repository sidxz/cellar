"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { useState } from "react";
import { type VocabularyField, useProtocolVocabulary } from "../hooks/use-protocol-vocabulary";

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  field: VocabularyField;
}

export function VocabularyAutocomplete({ value, onChange, placeholder, field }: Props) {
  const [focused, setFocused] = useState(false);
  const debounced = useDebounce(value, SEARCH_DEBOUNCE_MS);
  const { data } = useProtocolVocabulary(field, debounced);

  const suggestions = (data ?? [])
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
      placeholder={placeholder}
      inputClassName="h-9"
    />
  );
}
