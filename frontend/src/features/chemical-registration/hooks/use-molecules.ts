"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  Molecule,
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
    queryFn: () =>
      customInstance<Molecule[]>({
        url: "/api/v1/molecules",
        method: "GET",
        params: filters,
      }),
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
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
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
