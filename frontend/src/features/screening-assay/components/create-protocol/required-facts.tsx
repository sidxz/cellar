"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Label } from "@/shared/components/ui/label";
import type { ReactNode } from "react";
import type { ProtocolFacetSlot } from "../../hooks/use-protocol-facet-slots";
import { TargetMultiSelect } from "../target-multi-select";

/** The pickers that fill a name pattern's slots: `"target"` or a facet slot name (`{matrix}` is the assay format). */
export function factSlots(slots: Set<string>, followsTarget: boolean): string[] {
  const out: string[] = [];
  if (slots.has("target") || (slots.has("subject") && followsTarget)) out.push("target");
  if (slots.has("organism") || (slots.has("subject") && !followsTarget)) out.push("organism");
  if (slots.has("cell_line")) out.push("cell_line");
  if (slots.has("matrix")) out.push("assay_format");
  return out;
}

/** One facet slot's ontology picker with its label. */
export function FacetField({
  slot,
  value,
  onChange,
  hint,
  optional = false,
}: {
  slot: ProtocolFacetSlot;
  value: OntologyTerm[];
  onChange: (terms: OntologyTerm[]) => void;
  hint?: ReactNode;
  /** An optional slot of the name pattern: it changes the name only when filled. */
  optional?: boolean;
}) {
  return (
    <div className="grid gap-1.5">
      <Label>
        {slot.label}
        {optional && " (optional)"}
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

/** The facts the name is built from, right under the category: required ones, then optional ones. */
export function NameFacts({
  required,
  optional,
  facetSlots,
  annotations,
  onAnnotations,
  targetIds,
  onTargetIds,
  assayFormatHint,
}: {
  required: string[];
  optional: string[];
  facetSlots: ProtocolFacetSlot[];
  annotations: Record<string, OntologyTerm[]>;
  onAnnotations: (slot: string, terms: OntologyTerm[]) => void;
  targetIds: string[];
  onTargetIds: (ids: string[]) => void;
  assayFormatHint?: ReactNode;
}) {
  const field = (name: string, isOptional: boolean) => {
    if (name === "target") {
      return (
        <div key={name} className="grid gap-1.5">
          <Label>Target{isOptional && " (optional)"}</Label>
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
          hint={name === "assay_format" ? assayFormatHint : undefined}
          optional={isOptional}
        />
      )
    );
  };
  return [...required.map((n) => field(n, false)), ...optional.map((n) => field(n, true))];
}
