import { useListAlgorithmsApiV1SearchAlgorithmsGet } from "@/shared/lib/api/search/search";
import { STALE_TIME } from "@/shared/lib/query-defaults";

/** Single source of truth for similarity mode metadata.
 * Backend returns the registry; FE renders mode radios from this. */
export function useSearchAlgorithms() {
  return useListAlgorithmsApiV1SearchAlgorithmsGet({
    query: { staleTime: STALE_TIME.STATIC }, // registry is effectively static
  });
}
