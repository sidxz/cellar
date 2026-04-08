"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { Collection } from "@/features/research-organization/types";

const MOLECULES_KEY = ["molecules"];

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
