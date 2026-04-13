"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import {
  useOntologyDescendants,
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
  // When rootConceptId is set, use dropdown mode (finite list of descendants)
  // Otherwise, use search mode (type-ahead against BioPortal)
  const isDropdownMode = !!rootConceptId && ontologySources.length > 0;

  if (isDropdownMode) {
    return (
      <OntologyDropdown
        ontology={ontologySources[0]}
        rootConceptId={rootConceptId!}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
      />
    );
  }

  return (
    <OntologySearchMode
      ontologySources={ontologySources}
      rootConceptId={rootConceptId}
      value={value}
      onChange={onChange}
      allowFreeText={allowFreeText}
      placeholder={placeholder}
    />
  );
}

// ---------------------------------------------------------------------------
// Dropdown mode — for slots with root_concept_id (finite list)
// ---------------------------------------------------------------------------

function OntologyDropdown({
  ontology,
  rootConceptId,
  value,
  onChange,
  placeholder,
}: {
  ontology: string;
  rootConceptId: string;
  value: OntologyTerm[];
  onChange: (terms: OntologyTerm[]) => void;
  placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { data: descendants, isLoading } = useOntologyDescendants(
    ontology,
    rootConceptId,
  );

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const addTerm = (term: OntologyTerm) => {
    if (!value.some((t) => t.term_id === term.term_id)) {
      onChange([...value, term]);
    }
    setOpen(false);
  };

  const removeTerm = (termId: string) => {
    onChange(value.filter((t) => t.term_id !== termId));
  };

  const available = (descendants ?? []).filter(
    (d) => !value.some((v) => v.term_id === d.term_id),
  );

  return (
    <div ref={containerRef} className="relative">
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {value.map((term) => (
            <Badge key={term.term_id} variant="secondary" className="gap-1 pr-1">
              {term.label}
              <button
                type="button"
                onClick={() => removeTerm(term.term_id)}
                className="ml-0.5 rounded p-0.5 hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        className="w-full justify-between font-normal"
        onClick={() => setOpen(!open)}
      >
        <span className="text-muted-foreground">{placeholder}</span>
        <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
      </Button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-60 overflow-y-auto">
          {isLoading ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              Loading...
            </div>
          ) : available.length === 0 ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              {descendants?.length ? "All terms selected." : "No terms found."}
            </div>
          ) : (
            available.map((term) => (
              <button
                key={term.term_id}
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => addTerm(term)}
              >
                <span>{term.label}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Search mode — for slots without root_concept_id (type-ahead)
// ---------------------------------------------------------------------------

function OntologySearchMode({
  ontologySources,
  rootConceptId,
  value,
  onChange,
  allowFreeText,
  placeholder,
}: {
  ontologySources: string[];
  rootConceptId?: string | null;
  value: OntologyTerm[];
  onChange: (terms: OntologyTerm[]) => void;
  allowFreeText: boolean;
  placeholder: string;
}) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const filteredResults = (results ?? []).filter(
    (r) => !value.some((v) => v.term_id === r.term_id),
  );

  return (
    <div ref={containerRef} className="relative">
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
                className="ml-0.5 rounded p-0.5 hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

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
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
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
