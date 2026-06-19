import type { OntologyTerm } from "@/shared/components/ontology-search-input";

/** Build the create-payload facet map from the dialog's per-slot annotation
 *  state: keep only slots that actually have terms (mirrors the backend's
 *  `if terms` guard). Facets are persisted atomically as part of protocol
 *  creation — one transaction, no per-slot PUTs — so every slot lands together
 *  instead of racing on the aggregate version. */
export function ontologyAnnotationsPayload(
  annotations: Record<string, OntologyTerm[]>,
): Record<string, OntologyTerm[]> {
  return Object.fromEntries(Object.entries(annotations).filter(([, terms]) => terms.length > 0));
}
