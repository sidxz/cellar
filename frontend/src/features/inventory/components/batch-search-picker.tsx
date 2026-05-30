"use client";

import { Input } from "@/shared/components/ui/input";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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
  const debounced = useDebounce(searchTerm, 300);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data, isLoading } = useBatchesGlobal({ search: debounced, page_size: 20 });
  const results = debounced.length >= 2 ? (data?.items ?? []) : [];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Input
          value={displayValue}
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setIsOpen(e.target.value.length >= 2);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") onEnter?.();
          }}
          placeholder="Search batch # or compound…"
          className="pr-8"
          autoFocus
        />
        {value && (
          <button
            type="button"
            onClick={() => {
              setSearchTerm("");
              onClear();
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
            aria-label="Clear batch"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
          {isLoading && <div className="px-3 py-2 text-sm text-muted-foreground">Searching…</div>}
          {!isLoading && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-muted-foreground">No batches found.</div>
          )}
          {results.map((b) => (
            <button
              key={b.id}
              type="button"
              className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(b.batch_number);
              }}
            >
              <span className="font-mono text-xs text-muted-foreground">{b.batch_number}</span>
              <span className="mx-1.5">&mdash;</span>
              <span>{b.molecule_name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
