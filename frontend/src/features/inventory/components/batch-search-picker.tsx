"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { PICKER_RESULT_LIMIT, SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { useCallback, useState } from "react";
import { useBatchesGlobal } from "../hooks/use-batches";

interface BatchSearchPickerProps {
  /** Current batch reference (batch number or id) — shown when not actively searching. */
  value: string;
  onSelect: (batchNumber: string) => void;
  onClear: () => void;
  onEnter?: () => void;
}

/**
 * Search-and-pick a batch by number or compound name, replacing free-text entry.
 * Selecting stores the batch number (the API resolves it server-side). Mirrors
 * the MoleculeSelector pattern.
 */
export function BatchSearchPicker({ value, onSelect, onClear, onEnter }: BatchSearchPickerProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const debounced = useDebounce(searchTerm, SEARCH_DEBOUNCE_MS);
  const [isOpen, setIsOpen] = useState(false);

  const { data, isLoading } = useBatchesGlobal({
    search: debounced,
    page_size: PICKER_RESULT_LIMIT,
  });
  const results = debounced.length >= 2 ? (data?.items ?? []) : [];

  const handleSelect = useCallback(
    (batchNumber: string) => {
      setSearchTerm("");
      setIsOpen(false);
      onSelect(batchNumber);
    },
    [onSelect],
  );

  const displayValue = searchTerm !== "" ? searchTerm : value;
  const showDropdown = isOpen && debounced.length >= 2;

  return (
    <SearchCombobox
      searchValue={displayValue}
      onSearchChange={(next) => {
        setSearchTerm(next);
        setIsOpen(next.length >= 2);
      }}
      items={results}
      getItemKey={(b) => b.id}
      renderItem={(b) => (
        <span className="text-sm">
          <span className="font-mono text-xs text-muted-foreground">{b.batch_number}</span>
          <span className="mx-1.5">&mdash;</span>
          <span>{b.molecule_name}</span>
        </span>
      )}
      onSelect={(b) => handleSelect(b.batch_number)}
      isLoading={isLoading}
      open={showDropdown}
      onOpenChange={setIsOpen}
      onInputKeyDown={(e) => {
        if (e.key === "Enter") onEnter?.();
      }}
      placeholder="Search batch # or compound…"
      emptyMessage="No batches found."
      loadingMessage="Searching…"
      onClear={
        value
          ? () => {
              setSearchTerm("");
              onClear();
            }
          : undefined
      }
      clearAriaLabel="Clear batch"
      autoFocus
    />
  );
}
