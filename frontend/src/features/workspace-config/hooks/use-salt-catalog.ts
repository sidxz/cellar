"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";

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

const saltHooks = createCrudHooks<SaltEntry, CreateSaltEntryInput, UpdateSaltEntryInput>({
  entityName: "Salt entry",
  baseUrl: "/api/v1/salt-catalog",
  queryKey: SALT_CATALOG_KEY,
});

/** Custom list — supports activeOnly boolean flag. */
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

export const useCreateSaltEntry = saltHooks.useCreate;
export const useUpdateSaltEntry = saltHooks.useUpdate;
export const useDeleteSaltEntry = saltHooks.useDelete;
