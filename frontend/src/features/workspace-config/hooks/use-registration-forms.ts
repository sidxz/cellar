"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FieldOverride {
  field_definition_id: string;
  is_required?: boolean | null;
  default_value?: unknown;
  is_locked?: boolean;
  pick_list_subset?: string[] | null;
}

export interface RegistrationForm {
  id: string;
  workspace_id: string;
  name: string;
  applies_to: "molecule" | "batch";
  is_default: boolean;
  field_overrides: FieldOverride[];
  version: number;
}

export interface CreateRegistrationFormInput {
  name: string;
  applies_to: "molecule" | "batch";
  is_default?: boolean;
  field_overrides?: FieldOverride[];
}

export interface UpdateRegistrationFormInput {
  name?: string;
  is_default?: boolean;
  field_overrides?: FieldOverride[];
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

const REGISTRATION_FORMS_KEY = ["registration-forms"];

const formHooks = createCrudHooks<RegistrationForm, CreateRegistrationFormInput, UpdateRegistrationFormInput>({
  entityName: "Registration form",
  baseUrl: "/api/v1/registration-forms",
  queryKey: REGISTRATION_FORMS_KEY,
});

/** Custom list hook — supports `appliesTo` filtering. */
export function useRegistrationForms(appliesTo?: string) {
  return useQuery({
    queryKey: [...REGISTRATION_FORMS_KEY, appliesTo ?? "all"],
    queryFn: () => {
      const params: Record<string, string> = {};
      if (appliesTo) params.applies_to = appliesTo;
      return customInstance<RegistrationForm[]>({
        url: "/api/v1/registration-forms",
        method: "GET",
        params,
      });
    },
  });
}

export const useCreateRegistrationForm = formHooks.useCreate;
export const useUpdateRegistrationForm = formHooks.useUpdate;
export const useDeleteRegistrationForm = formHooks.useDelete;
