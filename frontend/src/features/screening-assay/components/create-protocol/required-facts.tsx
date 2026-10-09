"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Label } from "@/shared/components/ui/label";
import type { ReactNode } from "react";
import type { ProtocolFacetSlot } from "../../hooks/use-protocol-facet-slots";
import { TargetMultiSelect } from "../target-multi-select";

/** The pickers a category's name pattern needs: `"target"` or a facet slot name (`{matrix}` is the assay format). */
export function requiredFactSlots(needs: Set<string>, followsTarget: boolean): string[] {
  const out: string[] = [];
  if (needs.has("target") || (needs.has("subject") && followsTarget)) out.push("target");
  if (needs.has("organism") || (needs.has("subject") && !followsTarget)) out.push("organism");
  if (needs.has("cell_line")) out.push("cell_line");
  if (needs.has("matrix")) out.push("assay_format");
  return out;
}

/** One facet slot's ontology picker with its label. */
export function FacetField({
  slot,
  value,
  onChange,
  hint,
}: {
  slot: ProtocolFacetSlot;
  value: OntologyTerm[];
  onChange: (terms: OntologyTerm[]) => void;
  hint?: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label>
        {slot.label}
        {slot.is_required && <span className="ml-1 text-destructive">*</span>}
      </Label>
      <OntologySearchInput
        ontologySources={slot.ontology_sources}
        rootConceptId={slot.root_concept_id}
        value={value}
        onChange={onChange}
        allowFreeText={slot.allow_free_text}
        placeholder={`Search ${slot.ontology_sources.join(", ")}...`}
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function RequiredFacts({
  needs,
  followsTarget,
  facetSlots,
  annotations,
  onAnnotations,
  targetIds,
  onTargetIds,
}: {
  needs: Set<string>;
  followsTarget: boolean;
  facetSlots: ProtocolFacetSlot[];
  annotations: Record<string, OntologyTerm[]>;
  onAnnotations: (slot: string, terms: OntologyTerm[]) => void;
  targetIds: string[];
  onTargetIds: (ids: string[]) => void;
}) {
  return requiredFactSlots(needs, followsTarget).map((name) => {
    if (name === "target") {
      return (
        <div key={name} className="grid gap-1.5">
          <Label>Target</Label>
          <TargetMultiSelect value={targetIds} onChange={onTargetIds} />
        </div>
      );
    }
    const slot = facetSlots.find((s) => s.name === name);
    return (
      slot && (
        <FacetField
          key={name}
          slot={slot}
          value={annotations[name] ?? []}
          onChange={(terms) => onAnnotations(name, terms)}
        />
      )
    );
  });
}
