"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";

export interface OntologyTerm {
  term_id: string;
  label: string;
  ontology_source: string;
  uri: string | null;
}

export function useOntologySearch(
  query: string,
  ontologies: string[],
  enabled?: boolean,
) {
  return useQuery({
    queryKey: ["ontology-search", query, ontologies],
    queryFn: () =>
      customInstance<OntologyTerm[]>({
        url: "/api/v1/ontology/search",
        method: "GET",
        params: { q: query, ontologies: ontologies.join(",") },
      }),
    enabled: enabled !== false && query.length >= 2,
  });
}
