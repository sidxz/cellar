"use client";

import {
  type OntologyTerm,
  useOntologyDescendants,
  useOntologySearch,
} from "@/features/workspace-config/hooks/use-ontology-search";
import { SearchCombobox } from "@/shared/components/search-combobox";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { SEARCH_DEBOUNCE_MS, SEARCH_MIN_QUERY_LEN } from "@/shared/lib/timing";
import { ChevronDown, X } from "lucide-react";
import { useCallback, useState } from "react";

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
  const { data: descendants, isLoading } = useOntologyDescendants(ontology, rootConceptId);

  const addTerm = useCallback(
    (term: OntologyTerm) => {
      if (!value.some((t) => t.term_id === term.term_id)) {
        onChange([...value, term]);
      }
      setOpen(false);
    },
    [value, onChange],
  );

  const removeTerm = (termId: string) => {
    onChange(value.filter((t) => t.term_id !== termId));
  };

  const available = (descendants ?? []).filter((d) => !value.some((v) => v.term_id === d.term_id));

  return (
    <div className="relative">
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

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" className="w-full justify-between font-normal">
            <span className="text-muted-foreground">{placeholder}</span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command>
            <CommandInput placeholder="Filter terms…" />
            <CommandList>
              {isLoading ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">Loading...</div>
              ) : (
                <>
                  <CommandEmpty>
                    {descendants?.length ? "All terms selected." : "No terms found."}
                  </CommandEmpty>
                  <CommandGroup>
                    {available.map((term) => (
                      <CommandItem
                        key={term.term_id}
                        value={term.label}
                        onSelect={() => addTerm(term)}
                        className="cursor-pointer"
                      >
                        {term.label}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
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
  const debouncedQuery = useDebounce(query, SEARCH_DEBOUNCE_MS);
  const [showDropdown, setShowDropdown] = useState(false);

  const { data: results, isLoading } = useOntologySearch(
    debouncedQuery,
    ontologySources,
    showDropdown,
    rootConceptId,
  );

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
    <div className="relative">
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {value.map((term) => (
            <Badge key={term.term_id} variant="secondary" className="gap-1 pr-1">
              {term.label}
              <span className="text-[10px] text-muted-foreground">({term.ontology_source})</span>
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

      <SearchCombobox
        searchValue={query}
        onSearchChange={(value) => {
          setQuery(value);
          setShowDropdown(true);
        }}
        items={filteredResults}
        getItemKey={(term) => term.term_id}
        renderItem={(term) => (
          <span className="flex w-full items-center justify-between text-sm">
            <span>{term.label}</span>
            <Badge variant="outline" className="ml-2 text-[10px]">
              {term.ontology_source}
            </Badge>
          </span>
        )}
        onSelect={addTerm}
        isLoading={isLoading}
        open={showDropdown && debouncedQuery.length >= SEARCH_MIN_QUERY_LEN}
        onOpenChange={setShowDropdown}
        onInputFocus={() => {
          if (query.length >= SEARCH_MIN_QUERY_LEN) setShowDropdown(true);
        }}
        placeholder={placeholder}
        emptyMessage="No results found."
        footer={
          allowFreeText && query.trim() ? (
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
          ) : null
        }
      />
    </div>
  );
}
