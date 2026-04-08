"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import {
  useOntologySearch,
  type OntologyTerm,
} from "@/features/workspace-config/hooks/use-ontology-search";

export type { OntologyTerm };

export interface OntologySearchInputProps {
  ontologySources: string[];
  rootConceptId?: string | null;
  value: OntologyTerm[];
  onChange: (terms: OntologyTerm[]) => void;
  allowFreeText?: boolean;
  placeholder?: string;
}

export function OntologySearchInput({
  ontologySources,
  rootConceptId,
  value,
  onChange,
  allowFreeText = false,
  placeholder = "Search ontology terms...",
}: OntologySearchInputProps) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounce
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const { data: results, isLoading } = useOntologySearch(
    debouncedQuery,
    ontologySources,
    showDropdown,
    rootConceptId,
  );

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const addTerm = useCallback(
    (term: OntologyTerm) => {
      if (!value.some((t) => t.term_id === term.term_id)) {
        onChange([...value, term]);
      }
      setQuery("");
      setShowDropdown(false);
    },
    [value, onChange],
  );

  const removeTerm = useCallback(
    (termId: string) => {
      onChange(value.filter((t) => t.term_id !== termId));
    },
    [value, onChange],
  );

  const addFreeText = () => {
    const label = query.trim();
    if (!label) return;
    const term: OntologyTerm = {
      term_id: `free_text:${label}`,
      label,
      ontology_source: "free_text",
      uri: null,
    };
    addTerm(term);
  };

  // Filter out already-selected terms
  const filteredResults = (results ?? []).filter(
    (r) => !value.some((v) => v.term_id === r.term_id),
  );

  return (
    <div ref={containerRef} className="relative">
      {/* Selected terms */}
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {value.map((term) => (
            <Badge
              key={term.term_id}
              variant="secondary"
              className="gap-1 pr-1"
            >
              {term.label}
              <span className="text-[10px] text-muted-foreground">
                ({term.ontology_source})
              </span>
              <button
                type="button"
                onClick={() => removeTerm(term.term_id)}
                className="ml-0.5 rounded hover:bg-muted p-0.5"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {/* Search input */}
      <Input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setShowDropdown(true);
        }}
        onFocus={() => {
          if (query.length >= 2) setShowDropdown(true);
        }}
        placeholder={placeholder}
      />

      {/* Dropdown */}
      {showDropdown && debouncedQuery.length >= 2 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-60 overflow-y-auto">
          {isLoading ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              Searching...
            </div>
          ) : filteredResults.length === 0 ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              No results found.
            </div>
          ) : (
            filteredResults.map((term) => (
              <button
                key={term.term_id}
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-accent text-left"
                onClick={() => addTerm(term)}
              >
                <span>{term.label}</span>
                <Badge variant="outline" className="ml-2 text-[10px]">
                  {term.ontology_source}
                </Badge>
              </button>
            ))
          )}

          {allowFreeText && query.trim() && (
            <div className="border-t">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-full justify-start text-xs"
                onClick={addFreeText}
              >
                + Free Text: &quot;{query.trim()}&quot;
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
