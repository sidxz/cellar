"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";

export interface CustomFieldDefinition {
  id: string;
  workspace_id: string;
  name: string;
  label: string;
  data_type: "text" | "number" | "date" | "picklist" | "file" | "batch_link";
  applies_to: "molecule" | "batch" | "sample";
  is_required: boolean;
  default_value: unknown;
  display_order: number;
  pick_list_values: string[] | null;
  vocabulary_id: string | null;
  is_active: boolean;
  version: number;
}

export interface CreateCustomFieldInput {
  name: string;
  label: string;
  data_type: CustomFieldDefinition["data_type"];
  applies_to: CustomFieldDefinition["applies_to"];
  is_required?: boolean;
  default_value?: unknown;
  display_order?: number;
  pick_list_values?: string[] | null;
  vocabulary_id?: string | null;
}

export interface UpdateCustomFieldInput {
  label?: string;
  is_required?: boolean;
  default_value?: unknown;
  display_order?: number;
  pick_list_values?: string[] | null;
  vocabulary_id?: string | null;
  is_active?: boolean;
}

const CUSTOM_FIELDS_KEY = ["custom-fields"];

const cfHooks = createCrudHooks<CustomFieldDefinition, CreateCustomFieldInput, UpdateCustomFieldInput>({
  entityName: "Custom field",
  baseUrl: "/api/v1/custom-fields",
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
        url: "/api/v1/custom-fields",
        method: "GET",
        params,
      });
    },
  });
}

export const useCreateCustomField = cfHooks.useCreate;
export const useUpdateCustomField = cfHooks.useUpdate;
export const useDeleteCustomField = cfHooks.useDelete;
