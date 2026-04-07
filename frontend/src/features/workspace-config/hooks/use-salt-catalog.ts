"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

export interface SaltEntry {
  id: string;
  workspace_id: string;
  code: string;
  name: string;
  smiles: string;
  molecular_weight: number;
  is_default: boolean;
  is_active: boolean;
  version: number;
}

export interface CreateSaltEntryInput {
  code: string;
  name: string;
  smiles: string;
  molecular_weight: number;
}

export interface UpdateSaltEntryInput {
  name?: string;
  smiles?: string;
  molecular_weight?: number;
  is_active?: boolean;
}

const SALT_CATALOG_KEY = ["salt-catalog"];

export function useSaltCatalog(activeOnly = true) {
  return useQuery({
    queryKey: [...SALT_CATALOG_KEY, activeOnly],
    queryFn: () =>
      customInstance<SaltEntry[]>({
        url: "/api/v1/salt-catalog",
        method: "GET",
        params: { active_only: String(activeOnly) },
      }),
  });
}

export function useCreateSaltEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSaltEntryInput) =>
      customInstance<SaltEntry>({
        url: "/api/v1/salt-catalog",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SALT_CATALOG_KEY });
      showSuccess("Salt entry created");
    },
  });
}

export function useUpdateSaltEntry(saltId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateSaltEntryInput) =>
      customInstance<SaltEntry>({
        url: `/api/v1/salt-catalog/${saltId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SALT_CATALOG_KEY });
      showSuccess("Salt entry updated");
    },
  });
}

export function useDeleteSaltEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (saltId: string) =>
      customInstance<void>({
        url: `/api/v1/salt-catalog/${saltId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SALT_CATALOG_KEY });
      showSuccess("Salt entry deleted");
    },
  });
}
