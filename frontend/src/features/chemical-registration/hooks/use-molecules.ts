"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { PaginatedResponse } from "@/shared/types/pagination";
import type {
  Molecule,
  MoleculeIdentifier,
  RegisterMoleculeInput,
  RegistrationResponse,
  UpdateMoleculeInput,
} from "../types";

const MOLECULES_KEY = ["molecules"];

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

export function useMolecule(id: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, id],
    queryFn: () =>
      customInstance<Molecule>({
        url: `/api/v1/molecules/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

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

export function useUpdateMolecule(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateMoleculeInput) =>
      customInstance<Molecule>({
        url: `/api/v1/molecules/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
  });
}

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

  return useQuery({
    queryKey: [...MOLECULES_KEY, "search", params],
    queryFn: () =>
      customInstance<Molecule[]>({
        url: "/api/v1/molecules/search",
        method: "GET",
        params: queryParams,
      }),
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

// --- Identifiers ---

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

// --- Relationships ---

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
