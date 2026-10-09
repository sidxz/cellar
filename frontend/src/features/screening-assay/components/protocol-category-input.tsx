"use client";

import { useProtocolCategories } from "@/features/workspace-config/hooks/use-protocol-categories";
import { SearchableSelect } from "@/shared/components/searchable-select";
import { VocabularyAutocomplete } from "./vocabulary-autocomplete";

interface ProtocolCategoryInputProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Category picker shared by create and edit: a dropdown of the workspace's protocol
 * categories (Admin > Protocol Categories), or free-text autocomplete over existing
 * categories when the workspace has none yet.
 */
export function ProtocolCategoryInput({ value, onChange }: ProtocolCategoryInputProps) {
  const { data: categories } = useProtocolCategories();
  const terms = (categories ?? []).map((c) => c.label);

  if (terms.length === 0) {
    return (
      <VocabularyAutocomplete
        value={value}
        onChange={onChange}
        placeholder="e.g., Enzyme inhibition"
        field="category"
      />
    );
  }

  // An existing off-list value stays visible (and selectable) instead of rendering blank.
  const options = value && !terms.includes(value) ? [value, ...terms] : terms;
  return (
    <SearchableSelect
      options={options.map((t) => ({ value: t, label: t }))}
      value={value || null}
      onValueChange={(v) => onChange(v ?? "")}
      placeholder="Select category..."
      searchPlaceholder="Search categories..."
    />
  );
}
