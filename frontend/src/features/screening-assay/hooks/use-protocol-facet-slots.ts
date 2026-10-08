"use client";

import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import { useMemo } from "react";

// Standard facet slots (spec §5.3) — always present, on create AND on the
// protocol page. Admin-configured slots (useOntologySlots) override these by name.
// allow_free_text so a chemist is never blocked when a term isn't in the ontology.
const STANDARD_FACET_SLOTS = [
  { name: "organism", label: "Organism", ontology_sources: ["NCBITAXON"] },
  { name: "assay_format", label: "Assay format", ontology_sources: ["BAO"] },
  { name: "detection", label: "Detection method", ontology_sources: ["BAO"] },
] as const;

export interface ProtocolFacetSlot {
  id: string;
  name: string;
  label: string;
  ontology_sources: string[];
  root_concept_id: string | null;
  allow_free_text: boolean;
  is_required: boolean;
}

/** Admin-configured ontology slots plus the standard facets they don't override. */
export function useProtocolFacetSlots(): ProtocolFacetSlot[] {
  const { data: ontologySlots } = useOntologySlots();
  return useMemo(() => {
    const admin = (ontologySlots ?? []).map((s) => ({
      ...s,
      root_concept_id: s.root_concept_id ?? null,
    }));
    const adminNames = new Set(admin.map((s) => s.name));
    const standards = STANDARD_FACET_SLOTS.filter((s) => !adminNames.has(s.name)).map((s) => ({
      id: `std:${s.name}`,
      name: s.name,
      label: s.label,
      ontology_sources: [...s.ontology_sources],
      root_concept_id: null,
      allow_free_text: true,
      is_required: false,
    }));
    return [...admin, ...standards];
  }, [ontologySlots]);
}
