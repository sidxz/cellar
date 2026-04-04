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
