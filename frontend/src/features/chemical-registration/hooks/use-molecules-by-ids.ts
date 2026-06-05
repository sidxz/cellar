"use client";

import { listMoleculesApiV1MoleculesGet } from "@/shared/lib/api/molecules/molecules";
import { useQuery } from "@tanstack/react-query";

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
