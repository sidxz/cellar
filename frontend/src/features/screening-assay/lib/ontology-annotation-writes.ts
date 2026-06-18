import type { OntologyTerm } from "@/shared/components/ontology-search-input";

export interface OntologyAnnotationWrite {
  slot: string;
  terms: OntologyTerm[];
}

/** One write per slot that actually has terms — the create dialog persists
 *  these after the protocol exists (the create payload itself has no slot
 *  for ontology annotations). */
export function ontologyAnnotationWrites(
  annotations: Record<string, OntologyTerm[]>,
): OntologyAnnotationWrite[] {
  return Object.entries(annotations)
    .filter(([, terms]) => terms && terms.length > 0)
    .map(([slot, terms]) => ({ slot, terms }));
}
