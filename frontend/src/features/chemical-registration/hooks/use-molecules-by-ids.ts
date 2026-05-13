"use client";

import { useQuery } from "@tanstack/react-query";
import { listMoleculesApiV1MoleculesGet } from "@/shared/lib/api/molecules/molecules";

/**
 * Bulk-fetches molecules by id list (workspace-scoped).
 * Uses GET /api/v1/molecules?ids=<csv>.
 * The query key is stable for the same sorted id set.
 */
export function useMoleculesByIds(ids: string[]) {
  const sortedKey = [...ids].sort().join(",");
  return useQuery({
    queryKey: ["molecules", "by-ids", sortedKey],
    queryFn: () => listMoleculesApiV1MoleculesGet({ ids: sortedKey }),
    enabled: ids.length > 0,
  });
}
