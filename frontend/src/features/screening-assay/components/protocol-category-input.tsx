"use client";

import { useVocabularyTerms } from "@/features/workspace-config/hooks/use-vocabularies";
import { SearchableSelect } from "@/shared/components/searchable-select";
import { VocabularyAutocomplete } from "./vocabulary-autocomplete";

/** Workspace vocabulary that turns the protocol Category field into a fixed dropdown. */
export const PROTOCOL_CATEGORIES_VOCABULARY = "Protocol Categories";

interface ProtocolCategoryInputProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Category picker shared by create and edit: a dropdown of the workspace's
 * "Protocol Categories" vocabulary, or free-text autocomplete over existing
 * categories when the workspace hasn't defined one.
 */
export function ProtocolCategoryInput({ value, onChange }: ProtocolCategoryInputProps) {
  const terms = useVocabularyTerms(PROTOCOL_CATEGORIES_VOCABULARY);

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
