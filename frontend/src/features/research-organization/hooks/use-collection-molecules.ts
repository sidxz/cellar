"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { MembershipResult, MoleculeReference } from "../types";
import { COLLECTIONS_KEY } from "./query-keys";

function moleculesKey(collectionId: string) {
  return [...COLLECTIONS_KEY, collectionId, "molecules"];
}

export function useCollectionMolecules(
  collectionId: string | undefined,
  offset?: number,
  limit?: number,
) {
  return useQuery({
    queryKey: [...moleculesKey(collectionId ?? ""), { offset, limit }],
    queryFn: () =>
      customInstance<string[]>({
        url: `${API_V1}/collections/${collectionId}/molecules`,
        method: "GET",
        params: {
          ...(offset != null ? { offset: String(offset) } : {}),
          ...(limit != null ? { limit: String(limit) } : {}),
        },
      }),
    enabled: !!collectionId,
  });
}

export function useAddMolecules(collectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { references: MoleculeReference[] }) =>
      customInstance<MembershipResult>({
        url: `${API_V1}/collections/${collectionId}/molecules`,
        method: "POST",
        data,
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: moleculesKey(collectionId) });
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess(`Added ${result.added_count} molecule${result.added_count !== 1 ? "s" : ""}`);
    },
  });
}

export function useRemoveMolecules(collectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { molecule_ids: string[] }) =>
      customInstance<{ removed: number }>({
        url: `${API_V1}/collections/${collectionId}/molecules`,
        method: "DELETE",
        data,
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: moleculesKey(collectionId) });
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess(`Removed ${result.removed} molecule${result.removed !== 1 ? "s" : ""}`);
    },
  });
}
