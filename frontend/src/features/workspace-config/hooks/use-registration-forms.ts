"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

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
// Query keys
// ---------------------------------------------------------------------------

const REGISTRATION_FORMS_KEY = ["registration-forms"];

function buildQueryKey(appliesTo?: string) {
  return [...REGISTRATION_FORMS_KEY, appliesTo ?? "all"];
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useRegistrationForms(appliesTo?: string) {
  return useQuery({
    queryKey: buildQueryKey(appliesTo),
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

export function useCreateRegistrationForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRegistrationFormInput) =>
      customInstance<RegistrationForm>({
        url: "/api/v1/registration-forms",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REGISTRATION_FORMS_KEY });
      showSuccess("Registration form created");
    },
  });
}

export function useUpdateRegistrationForm(formId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateRegistrationFormInput) =>
      customInstance<RegistrationForm>({
        url: `/api/v1/registration-forms/${formId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REGISTRATION_FORMS_KEY });
      showSuccess("Registration form updated");
    },
  });
}

export function useDeleteRegistrationForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formId: string) =>
      customInstance<void>({
        url: `/api/v1/registration-forms/${formId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REGISTRATION_FORMS_KEY });
      showSuccess("Registration form deleted");
    },
  });
}
