import { useListAlgorithmsApiV1SearchAlgorithmsGet } from "@/shared/lib/api/search/search";

/** Single source of truth for similarity mode metadata.
 * Backend returns the registry; FE renders mode radios from this. */
export function useSearchAlgorithms() {
  return useListAlgorithmsApiV1SearchAlgorithmsGet({
    query: { staleTime: Number.POSITIVE_INFINITY }, // registry is effectively static
  });
}
