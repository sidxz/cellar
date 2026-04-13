"use client";

import { useState } from "react";
import { Check, ChevronsUpDown, Plus, Trash2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { cn } from "@/shared/lib/utils";
import { useCollections } from "../../hooks/use-collections";
import type { CollectionCriterion, SearchCriterion } from "../../types";

// ─── Extended type with negate support ──────────────────────────────────────

/** Internal extension — `negate` means "NOT in this collection" */
export interface CollectionTermValue {
  collection_id: string;
  negate: boolean;
}

function defaultCollectionTerm(): CollectionTermValue {
  return { collection_id: "", negate: false };
}

// ─── Single collection term ─────────────────────────────────────────────────

function CollectionTerm({
  term,
  onChange,
  onRemove,
}: {
  term: CollectionTermValue;
  onChange: (t: CollectionTermValue) => void;
  onRemove: () => void;
}) {
  const { data: collections } = useCollections();
  const [open, setOpen] = useState(false);

  const selected = collections?.find((c) => c.id === term.collection_id);

  return (
    <div className="flex items-center gap-2 mb-1.5">
      <div className="w-20">
        <Select
          value={term.negate ? "not_in" : "in"}
          onValueChange={(v) => onChange({ ...term, negate: v === "not_in" })}
        >
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="in">In</SelectItem>
            <SelectItem value="not_in">Not In</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                "flex h-8 w-full items-center justify-between rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
                !term.collection_id && "text-muted-foreground",
              )}
            >
              <span className="truncate">
                {selected
                  ? `${selected.name} (${selected.molecule_count})`
                  : "Select collection…"}
              </span>
              <ChevronsUpDown className="ml-1 h-3 w-3 shrink-0 opacity-50" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-0" align="start">
            <Command>
              <CommandInput placeholder="Search collections…" className="h-8 text-sm" />
              <CommandList>
                <CommandEmpty>No collections found.</CommandEmpty>
                <CommandGroup>
                  {collections?.map((c) => (
                    <CommandItem
                      key={c.id}
                      value={c.name}
                      onSelect={() => {
                        onChange({ ...term, collection_id: c.id });
                        setOpen(false);
                      }}
                      className="text-sm"
                    >
                      <Check
                        className={cn(
                          "mr-1.5 h-3 w-3",
                          term.collection_id === c.id ? "opacity-100" : "opacity-0",
                        )}
                      />
                      {c.name} ({c.molecule_count})
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <button
        type="button"
        onClick={onRemove}
        className="text-muted-foreground/40 hover:text-destructive"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

interface CollectionSectionProps {
  /** Terms with in/not-in semantics */
  terms: CollectionTermValue[];
  onChange: (terms: CollectionTermValue[]) => void;
}

export function CollectionSection({ terms, onChange }: CollectionSectionProps) {
  function addTerm() {
    onChange([...terms, defaultCollectionTerm()]);
  }

  function updateTerm(index: number, updated: CollectionTermValue) {
    onChange(terms.map((t, i) => (i === index ? updated : t)));
  }

  function removeTerm(index: number) {
    onChange(terms.filter((_, i) => i !== index));
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Collections
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>

      {terms.length === 0 && (
        <p className="text-sm italic text-muted-foreground/50">
          No collection filters.
        </p>
      )}

      <div>
        {terms.map((t, i) => (
          <CollectionTerm
            key={`collection-${i}`}
            term={t}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Helpers: convert between internal term format and SearchCriterion ─────

export function termsToCollectionCriteria(terms: CollectionTermValue[]): SearchCriterion[] {
  return terms
    .filter((t) => t.collection_id)
    .map((t): SearchCriterion => ({
      type: "collection" as const,
      collection_id: t.collection_id,
      negate: t.negate || undefined,
    }));
}

export function collectionCriteriaToTerms(criteria: SearchCriterion[]): CollectionTermValue[] {
  return criteria
    .filter((c): c is CollectionCriterion & { negate?: boolean } => c.type === "collection")
    .map((c) => ({
      collection_id: c.collection_id,
      negate: !!c.negate,
    }));
}
