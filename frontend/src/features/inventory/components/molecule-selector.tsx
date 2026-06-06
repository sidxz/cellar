"use client";

import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import type { Molecule } from "@/features/chemical-registration/types";
import { SearchCombobox } from "@/shared/components/search-combobox";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { useCallback, useMemo, useRef, useState } from "react";

interface MoleculeSelectorProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function MoleculeSelector({ selectedId, onSelect }: MoleculeSelectorProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const debouncedTerm = useDebounce(searchTerm, SEARCH_DEBOUNCE_MS);
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: results, isLoading } = useMoleculeSearch(debouncedTerm);

  // Derive selectedMolecule from results + selectedId — no separate state needed
  const selectedMolecule = useMemo(
    () => results?.find((m) => m.id === selectedId) ?? null,
    [results, selectedId],
  );

  const handleSelect = useCallback(
    (mol: Molecule) => {
      setSearchTerm("");
      setIsOpen(false);
      onSelect(mol.id);
    },
    [onSelect],
  );

  const handleClear = useCallback(() => {
    setSearchTerm("");
    onSelect(null);
    inputRef.current?.focus();
  }, [onSelect]);

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchTerm(value);
      setIsOpen(value.length >= 2);
      // If user types while a molecule is selected, clear the selection
      if (selectedMolecule) {
        onSelect(null);
      }
    },
    [selectedMolecule, onSelect],
  );

  const displayValue = selectedMolecule
    ? `${selectedMolecule.registration_number} — ${selectedMolecule.name}`
    : searchTerm;

  const showDropdown = isOpen && debouncedTerm.length >= 2;

  return (
    <SearchCombobox
      className="min-w-[240px]"
      searchValue={displayValue}
      onSearchChange={handleSearchChange}
      items={results ?? []}
      getItemKey={(mol) => mol.id}
      renderItem={(mol) => (
        <span className="text-sm">
          <span className="font-mono text-xs text-muted-foreground">{mol.registration_number}</span>
          <span className="mx-1.5">&mdash;</span>
          <span>{mol.name}</span>
        </span>
      )}
      onSelect={handleSelect}
      isLoading={isLoading}
      open={showDropdown}
      onOpenChange={setIsOpen}
      onInputFocus={() => {
        if (debouncedTerm.length >= 2 && !selectedMolecule) {
          setIsOpen(true);
        }
      }}
      placeholder="Search compounds..."
      emptyMessage="No compounds found."
      onClear={selectedMolecule ? handleClear : undefined}
      clearAriaLabel="Clear selection"
      inputRef={inputRef}
    />
  );
}
