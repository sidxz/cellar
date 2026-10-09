"use client";

import {
  type OntologyTerm,
  useTermsInUse,
} from "@/features/workspace-config/hooks/use-ontology-search";
import { useProtocolCategories } from "@/features/workspace-config/hooks/use-protocol-categories";
import { useProtocolForms } from "@/features/workspace-config/hooks/use-protocol-forms";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { useQueries } from "@tanstack/react-query";
import {
  type ProtocolCsvRow,
  type ResolveContext,
  usedHereMatches,
} from "../lib/protocol-csv-import";
import { useProtocolFacetSlots } from "./use-protocol-facet-slots";
import { useTargets } from "./use-targets";

const TERM_SLOTS = ["organism", "cell_line"] as const;

/**
 * What the CSV rows resolve against: categories, forms, targets, the terms used here, and one
 * exact lookup (`exact_only`: a common name, or the ontology's exact label/synonym matches) per
 * distinct value nothing used here matches. Null until the lists have loaded.
 */
export function useProtocolCsvContext(rows: ProtocolCsvRow[]): ResolveContext | null {
  const categories = useProtocolCategories();
  const forms = useProtocolForms();
  const targets = useTargets();
  const organismsHere = useTermsInUse("organism");
  const cellLinesHere = useTermsInUse("cell_line");
  const facetSlots = useProtocolFacetSlots();
  const usedHere = { organism: organismsHere.data ?? [], cell_line: cellLinesHere.data ?? [] };

  // Look up only what the terms used here don't settle, so wait for them first.
  const hereLoaded = !organismsHere.isPending && !cellLinesHere.isPending;
  const lookups = [
    ...new Set(
      (hereLoaded ? rows : []).flatMap((r) =>
        TERM_SLOTS.filter((slot) => {
          const q = r[slot].trim();
          return q && usedHereMatches(q, usedHere[slot]).length !== 1;
        }).map((slot) => JSON.stringify([slot, r[slot].trim()])),
      ),
    ),
  ].map((key) => JSON.parse(key) as [(typeof TERM_SLOTS)[number], string]);

  const results = useQueries({
    queries: lookups.map(([slot, q]) => {
      const def = facetSlots.find((s) => s.name === slot);
      const sources = def?.ontology_sources ?? [];
      return {
        queryKey: ["ontology-search", "exact", q, sources, def?.root_concept_id ?? null],
        queryFn: () =>
          sources.length === 0
            ? Promise.resolve([] as OntologyTerm[])
            : customInstance<OntologyTerm[]>({
                url: `${API_V1}/ontology/search`,
                method: "GET",
                params: {
                  q,
                  ontologies: sources.join(","),
                  exact_only: true,
                  ...(def?.root_concept_id ? { subtree_root_id: def.root_concept_id } : {}),
                },
              }),
        staleTime: STALE_TIME.LONG,
        retry: false,
      };
    }),
  });

  const lists = [categories, forms, targets, organismsHere, cellLinesHere];
  if (lists.some((q) => q.isPending)) return null;
  // A list that failed to load resolves nothing, so its values wait for a pick.
  return {
    categories: categories.data ?? [],
    forms: forms.data ?? [],
    targets: targets.data ?? [],
    usedHere,
    exactHits: (slot, q) => {
      const i = lookups.findIndex(([s, query]) => s === slot && query === q);
      const result = results[i];
      if (!result) return undefined;
      // A failed lookup leaves the value for the chemist to pick; it never guesses.
      return result.isError ? [] : result.data;
    },
  };
}
