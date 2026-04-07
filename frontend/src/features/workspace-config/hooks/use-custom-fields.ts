"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

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

function buildQueryKey(appliesTo?: string, activeOnly?: boolean) {
  return [...CUSTOM_FIELDS_KEY, appliesTo ?? "all", activeOnly ?? true];
}

export function useCustomFields(
  appliesTo?: string,
  activeOnly?: boolean
) {
  return useQuery({
    queryKey: buildQueryKey(appliesTo, activeOnly),
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

export function useCreateCustomField() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateCustomFieldInput) =>
      customInstance<CustomFieldDefinition>({
        url: "/api/v1/custom-fields",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CUSTOM_FIELDS_KEY });
      showSuccess("Custom field created");
    },
  });
}

export function useUpdateCustomField(fieldId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateCustomFieldInput) =>
      customInstance<CustomFieldDefinition>({
        url: `/api/v1/custom-fields/${fieldId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CUSTOM_FIELDS_KEY });
      showSuccess("Custom field updated");
    },
  });
}

export function useDeleteCustomField() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fieldId: string) =>
      customInstance<void>({
        url: `/api/v1/custom-fields/${fieldId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CUSTOM_FIELDS_KEY });
      showSuccess("Custom field deleted");
    },
  });
}
