"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { PaginatedResponse } from "@/shared/types/pagination";
import type {
  Molecule,
  MoleculeIdentifier,
  RegisterMoleculeInput,
  RegistrationResponse,
  UpdateMoleculeInput,
} from "../types";

const MOLECULES_KEY = ["molecules"];

const moleculeHooks = createCrudHooks<Molecule, RegisterMoleculeInput, UpdateMoleculeInput>({
  entityName: "Compound",
  baseUrl: "/api/v1/molecules",
  queryKey: MOLECULES_KEY,
});

export const useMolecule = moleculeHooks.useGet;
export const useUpdateMolecule = moleculeHooks.useUpdate;

/** Custom list — unwraps PaginatedResponse and supports filters. */
export function useMolecules(filters?: {
  molecule_type?: string;
  lifecycle_stage?: string;
  structure_status?: string;
}) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, filters],
    queryFn: async () => {
      const page = await customInstance<PaginatedResponse<Molecule>>({
        url: "/api/v1/molecules",
        method: "GET",
        params: filters,
      });
      return page.items;
    },
  });
}

/** Custom create — returns RegistrationResponse, not Molecule. */
export function useRegisterMolecule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterMoleculeInput) =>
      customInstance<RegistrationResponse>({
        url: "/api/v1/molecules",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Compound registered");
    },
  });
}

// --- Custom search hooks ---

export function useMoleculeSearch(q: string) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, "search-text", q],
    queryFn: async () => {
      const page = await customInstance<PaginatedResponse<Molecule>>({
        url: "/api/v1/molecules",
        method: "GET",
        params: { q, limit: "20" },
      });
      return page.items;
    },
    enabled: q.length >= 2,
  });
}

export interface SimilaritySearchResult {
  molecule: Molecule;
  similarity: number;
}

export type SearchResult = {
  molecule: Molecule;
  similarity: number | null;
};

interface StructureSearchResponse {
  search_type: string;
  molecules: Molecule[] | null;
  similarity_results: SimilaritySearchResult[] | null;
  count: number;
}

export function useSearchMolecules(params: {
  search_type: string;
  query: string;
  threshold?: number;
} | undefined) {
  const queryParams = params
    ? {
        search_type: params.search_type,
        query: params.query,
        ...(params.threshold !== undefined
          ? { threshold: String(params.threshold) }
          : {}),
      }
    : undefined;

  const isSimilarity = params?.search_type === "similarity";

  return useQuery({
    queryKey: [...MOLECULES_KEY, "search", params],
    queryFn: async () => {
      const data = await customInstance<StructureSearchResponse>({
        url: "/api/v1/molecules/search",
        method: "GET",
        params: queryParams,
      });
      if (isSimilarity && data.similarity_results) {
        return data.similarity_results.map((r) => ({
          molecule: r.molecule,
          similarity: r.similarity,
        }));
      }
      return (data.molecules ?? []).map((m) => ({
        molecule: m,
        similarity: null,
      }));
    },
    enabled: !!params?.query,
  });
}

export function useMoleculeByIdentifier(identifier: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, "by-identifier", identifier],
    queryFn: () =>
      customInstance<Molecule>({
        url: `/api/v1/molecules/by-identifier/${identifier}`,
        method: "GET",
      }),
    enabled: !!identifier,
  });
}

// --- Identifiers (nested under molecule) ---

export function useAddIdentifier(moleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      identifier: string;
      identifier_type: string;
      source: string;
    }) =>
      customInstance<MoleculeIdentifier[]>({
        url: `/api/v1/molecules/${moleculeId}/identifiers`,
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
  });
}

export function useRemoveIdentifier(moleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (identifierId: string) =>
      customInstance<void>({
        url: `/api/v1/molecules/${moleculeId}/identifiers/${identifierId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
  });
}

// --- Relationships (nested under molecule) ---

export function useRelationships(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, moleculeId, "relationships"],
    queryFn: () =>
      customInstance<
        Array<{
          id: string;
          source_molecule_id: string;
          target_molecule_id: string;
          relationship_type: string;
          notes: string | null;
          created_by: string;
          created_at: string;
        }>
      >({
        url: `/api/v1/molecules/${moleculeId}/relationships`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

export function useCreateRelationship(moleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      target_molecule_id: string;
      relationship_type: string;
      notes?: string;
    }) =>
      customInstance<unknown>({
        url: `/api/v1/molecules/${moleculeId}/relationships`,
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
  });
}

export function useDeleteRelationship(moleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (relationshipId: string) =>
      customInstance<void>({
        url: `/api/v1/molecules/${moleculeId}/relationships/${relationshipId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Relationship removed");
    },
  });
}
