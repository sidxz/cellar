"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { EnrichedSearchResponse } from "@/features/research-organization/hooks/use-search";
import type {
  ExecuteSearchInput,
  CollectionCriterion,
  ScaffoldCriterion,
  GroupCriterion,
} from "@/features/research-organization/types";

export interface UseCollectionScaffoldSearchOptions {
  collectionId: string;
  /** Scaffold SMILES to OR together server-side via IN; order-independent for caching. */
  scaffoldSmiles: string[];
  /** Defaults to true when collectionId + scaffoldSmiles.length > 0. */
  enabled?: boolean;
  /** Page size; default 10000 — same as useCollectionSearch. */
  limit?: number;
}

/**
 * Stable cache key for `useCollectionScaffoldSearch`. Exported so callers
 * (e.g. invalidation flows) can build the same key and so tests can verify
 * input-order independence.
 */
export function scaffoldSearchQueryKey(
  collectionId: string,
  scaffoldSmiles: string[],
): readonly unknown[] {
  return [
    "collection-scaffold-search",
    collectionId,
    [...scaffoldSmiles].sort().join("\n"),
  ];
}

/**
 * V4 Path A — fetches the enriched molecule list for `collectionId`
 * filtered to members whose Bemis-Murcko scaffold is in `scaffoldSmiles`.
 * The BE composes `collection_id` AND `bemis_murcko_smiles IN (...)`
 * via the existing search engine + the `exact_match_in` criterion mode.
 *
 * Cap: 500 scaffolds per request (enforced server-side).
 */
export function useCollectionScaffoldSearch({
  collectionId,
  scaffoldSmiles,
  enabled,
  limit = 10000,
}: UseCollectionScaffoldSearchOptions) {
  const effectiveEnabled =
    (enabled ?? true) && Boolean(collectionId) && scaffoldSmiles.length > 0;

  return useQuery({
    queryKey: scaffoldSearchQueryKey(collectionId, scaffoldSmiles),
    enabled: effectiveEnabled,
    queryFn: async () => {
      const collectionCriterion: CollectionCriterion = {
        type: "collection",
        collection_id: collectionId,
      };
      const scaffoldCriterion: ScaffoldCriterion = {
        type: "scaffold",
        mode: "exact_match_in",
        scaffold_smiles_list: scaffoldSmiles,
      };
      const groupCriterion: GroupCriterion = {
        type: "group",
        logic: "and",
        criteria: [collectionCriterion, scaffoldCriterion],
      };
      const input: ExecuteSearchInput = {
        query: {
          logic: "and",
          criteria: [groupCriterion],
        },
      };
      return customInstance<EnrichedSearchResponse>({
        url: "/api/v1/search/execute",
        method: "POST",
        data: input,
        params: { limit: String(limit) },
      });
    },
  });
}
