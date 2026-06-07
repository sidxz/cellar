"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateRegistrationFormBody,
  RegistrationFormResponse,
  UpdateRegistrationFormBody,
} from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// CLIENT-SIDE working type — NOT a backend DTO. The backend types each entry of
// `field_overrides` as an opaque `dict` (response/body alike), so the generated
// item type is `{ [key: string]: unknown }`. This is the FE's structured view of
// one override, used by the registration-form editor; it is read out of / written
// into the opaque generated array at the consumption edge.
export interface FieldOverride {
  field_definition_id: string;
  is_required?: boolean | null;
  default_value?: unknown;
  is_locked?: boolean;
  pick_list_subset?: string[] | null;
}

// Aliases of the orval-generated DTOs (source of truth).
export type RegistrationForm = RegistrationFormResponse;
export type CreateRegistrationFormInput = CreateRegistrationFormBody;
export type UpdateRegistrationFormInput = UpdateRegistrationFormBody;

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

const REGISTRATION_FORMS_KEY = ["registration-forms"];

const formHooks = createCrudHooks<
  RegistrationForm,
  CreateRegistrationFormInput,
  UpdateRegistrationFormInput
>({
  entityName: "Registration form",
  baseUrl: `${API_V1}/registration-forms`,
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
        url: `${API_V1}/registration-forms`,
        method: "GET",
        params,
      });
    },
  });
}

export const useCreateRegistrationForm = formHooks.useCreate;
export const useUpdateRegistrationForm = formHooks.useUpdate;
export const useDeleteRegistrationForm = formHooks.useDelete;
