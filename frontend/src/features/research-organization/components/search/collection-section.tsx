"use client";

import { Plus, Trash2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
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

  return (
    <div className="flex items-center gap-2 mb-1.5">
      <div className="w-20">
        <Select
          value={term.negate ? "not_in" : "in"}
          onValueChange={(v) => onChange({ ...term, negate: v === "not_in" })}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="in">In</SelectItem>
            <SelectItem value="not_in">Not In</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1">
        <Select
          value={term.collection_id || undefined}
          onValueChange={(v) => onChange({ ...term, collection_id: v })}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue placeholder="Select collection..." />
          </SelectTrigger>
          <SelectContent>
            {collections?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name} ({c.molecule_count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Collections
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80"
        >
          <Plus className="h-3 w-3" /> Add a term
        </button>
      </div>

      {terms.length === 0 && (
        <p className="text-xs italic text-muted-foreground/50">
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
