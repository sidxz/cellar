"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { OntologyTermResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

// Alias of the orval-generated DTO (source of truth).
export type OntologyTerm = OntologyTermResponse;

export function useOntologyDescendants(ontology: string, rootConceptId: string, enabled?: boolean) {
  return useQuery({
    queryKey: ["ontology-descendants", ontology, rootConceptId],
    queryFn: () =>
      customInstance<OntologyTerm[]>({
        url: `${API_V1}/ontology/descendants`,
        method: "GET",
        params: { ontology, root_concept_id: rootConceptId },
      }),
    enabled: enabled !== false && !!ontology && !!rootConceptId,
    staleTime: 30 * 60 * 1000, // 30 min — ontology trees don't change
  });
}

export function useOntologySearch(
  query: string,
  ontologies: string[],
  enabled?: boolean,
  subtreeRootId?: string | null,
) {
  return useQuery({
    queryKey: ["ontology-search", query, ontologies, subtreeRootId],
    queryFn: () =>
      customInstance<OntologyTerm[]>({
        url: `${API_V1}/ontology/search`,
        method: "GET",
        params: {
          q: query,
          ontologies: ontologies.join(","),
          ...(subtreeRootId ? { subtree_root_id: subtreeRootId } : {}),
        },
      }),
    enabled: enabled !== false && query.length >= 2,
  });
}
