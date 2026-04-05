"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import type { Molecule } from "@/features/chemical-registration/types";

interface MoleculeSelectorProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function MoleculeSelector({
  selectedId,
  onSelect,
}: MoleculeSelectorProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedTerm, setDebouncedTerm] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [selectedMolecule, setSelectedMolecule] = useState<Molecule | null>(
    null,
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: results, isLoading } = useMoleculeSearch(debouncedTerm);

  // Debounce the search term (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // When results arrive and contain the already-selected molecule, capture it
  // (handles initial display when selectedId is set externally)
  useEffect(() => {
    if (selectedId && results) {
      const match = results.find((m) => m.id === selectedId);
      if (match) {
        setSelectedMolecule(match);
      }
    }
  }, [selectedId, results]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = useCallback(
    (mol: Molecule) => {
      setSelectedMolecule(mol);
      setSearchTerm("");
      setDebouncedTerm("");
      setIsOpen(false);
      onSelect(mol.id);
    },
    [onSelect],
  );

  const handleClear = useCallback(() => {
    setSelectedMolecule(null);
    setSearchTerm("");
    setDebouncedTerm("");
    onSelect(null);
    inputRef.current?.focus();
  }, [onSelect]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchTerm(e.target.value);
      if (e.target.value.length >= 2) {
        setIsOpen(true);
      } else {
        setIsOpen(false);
      }
      // If user types while a molecule is selected, clear the selection
      if (selectedMolecule) {
        setSelectedMolecule(null);
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
    <div ref={containerRef} className="relative min-w-[240px]">
      <div className="relative">
        <Input
          ref={inputRef}
          value={displayValue}
          onChange={handleInputChange}
          onFocus={() => {
            if (debouncedTerm.length >= 2 && !selectedMolecule) {
              setIsOpen(true);
            }
          }}
          placeholder="Search compounds..."
          className="pr-8"
        />
        {selectedMolecule && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
          {isLoading && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              Searching...
            </div>
          )}
          {!isLoading && results && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              No compounds found.
            </div>
          )}
          {results?.map((mol) => (
            <button
              key={mol.id}
              type="button"
              className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onMouseDown={(e) => {
                // Use mousedown to fire before onBlur
                e.preventDefault();
                handleSelect(mol);
              }}
            >
              <span className="font-mono text-xs text-muted-foreground">
                {mol.registration_number}
              </span>
              <span className="mx-1.5">&mdash;</span>
              <span>{mol.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
