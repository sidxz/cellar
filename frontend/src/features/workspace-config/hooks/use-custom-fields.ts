"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateCustomFieldBody,
  CustomFieldResponse,
  UpdateCustomFieldBody,
} from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

// Aliases of the orval-generated DTOs (source of truth). The backend types
// `data_type` / `applies_to` as bare `str`, so the generated shapes widen them
// to `string`; the custom-field editor narrows them via its zod enums at the
// consumption edge. The allowed values are documented by these client-side unions.
export type CustomFieldDataType = "text" | "number" | "date" | "picklist" | "file" | "batch_link";
export type CustomFieldAppliesTo = "molecule" | "batch" | "sample";

export type CustomFieldDefinition = CustomFieldResponse;
export type CreateCustomFieldInput = CreateCustomFieldBody;
export type UpdateCustomFieldInput = UpdateCustomFieldBody;

const CUSTOM_FIELDS_KEY = ["custom-fields"];

const cfHooks = createCrudHooks<
  CustomFieldDefinition,
  CreateCustomFieldInput,
  UpdateCustomFieldInput
>({
  entityName: "Custom field",
  baseUrl: `${API_V1}/custom-fields`,
  queryKey: CUSTOM_FIELDS_KEY,
});

/** Custom list hook — supports `appliesTo` and `activeOnly` filtering. */
export function useCustomFields(appliesTo?: string, activeOnly?: boolean) {
  return useQuery({
    queryKey: [...CUSTOM_FIELDS_KEY, appliesTo ?? "all", activeOnly ?? true],
    queryFn: () => {
      const params: Record<string, string> = {};
      if (appliesTo) params.applies_to = appliesTo;
      if (activeOnly !== undefined) params.active_only = String(activeOnly);
      return customInstance<CustomFieldDefinition[]>({
        url: `${API_V1}/custom-fields`,
        method: "GET",
        params,
      });
    },
  });
}

export const useCreateCustomField = cfHooks.useCreate;
export const useUpdateCustomField = cfHooks.useUpdate;
export const useDeleteCustomField = cfHooks.useDelete;
