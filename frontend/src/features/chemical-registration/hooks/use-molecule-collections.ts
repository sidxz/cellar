"use client";

import type { Collection } from "@/features/research-organization/types";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { MOLECULES_KEY } from "./query-keys";

export function useMoleculeCollections(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, moleculeId, "collections"],
    queryFn: () =>
      customInstance<Collection[]>({
        url: `/api/v1/molecules/${moleculeId}/collections`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
