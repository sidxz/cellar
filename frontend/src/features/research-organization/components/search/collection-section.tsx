"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
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
    <div className="flex items-end gap-2">
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Mode</Label>
        <Select
          value={term.negate ? "not_in" : "in"}
          onValueChange={(v) => onChange({ ...term, negate: v === "not_in" })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="in">In</SelectItem>
            <SelectItem value="not_in">Not In</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="w-64">
        <Label className="text-xs text-muted-foreground">Collection</Label>
        <Select
          value={term.collection_id || undefined}
          onValueChange={(v) => onChange({ ...term, collection_id: v })}
        >
          <SelectTrigger className="h-9">
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

      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
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
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Collections</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={addTerm}
        >
          <Plus className="mr-1 h-3 w-3" />
          Add a term
        </Button>
      </div>

      {terms.length === 0 && (
        <p className="text-xs text-muted-foreground py-1">
          No collection filters. Click "Add a term" to filter by collection membership.
        </p>
      )}

      <div className="space-y-2">
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
