"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateSaltEntryBody,
  SaltEntryResponse,
  UpdateSaltEntryBody,
} from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

// Aliases of the orval-generated DTOs (source of truth).
export type SaltEntry = SaltEntryResponse;
export type CreateSaltEntryInput = CreateSaltEntryBody;
export type UpdateSaltEntryInput = UpdateSaltEntryBody;

const SALT_CATALOG_KEY = ["salt-catalog"];

const saltHooks = createCrudHooks<SaltEntry, CreateSaltEntryInput, UpdateSaltEntryInput>({
  entityName: "Salt entry",
  baseUrl: `${API_V1}/salt-catalog`,
  queryKey: SALT_CATALOG_KEY,
});

/** Custom list — supports activeOnly boolean flag. */
export function useSaltCatalog(activeOnly = true) {
  return useQuery({
    queryKey: [...SALT_CATALOG_KEY, activeOnly],
    queryFn: () =>
      customInstance<SaltEntry[]>({
        url: `${API_V1}/salt-catalog`,
        method: "GET",
        params: { active_only: String(activeOnly) },
      }),
  });
}

export const useCreateSaltEntry = saltHooks.useCreate;
export const useUpdateSaltEntry = saltHooks.useUpdate;
export const useDeleteSaltEntry = saltHooks.useDelete;
