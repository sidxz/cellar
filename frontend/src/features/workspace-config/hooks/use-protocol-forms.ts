"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

export interface ProtocolForm {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  protocol_type: string | null;
  is_default: boolean;
  readout_templates: Array<Record<string, unknown>>;
  condition_templates: Array<Record<string, unknown>> | null;
  ontology_defaults: Array<Record<string, unknown>> | null;
}

export interface CreateProtocolFormInput {
  name: string;
  description?: string | null;
  protocol_type?: string | null;
  is_default?: boolean;
  readout_templates?: Array<Record<string, unknown>>;
  condition_templates?: Array<Record<string, unknown>> | null;
  ontology_defaults?: Array<Record<string, unknown>> | null;
}

export interface UpdateProtocolFormInput {
  name?: string;
  description?: string | null;
  protocol_type?: string | null;
  is_default?: boolean;
  readout_templates?: Array<Record<string, unknown>>;
  condition_templates?: Array<Record<string, unknown>> | null;
  ontology_defaults?: Array<Record<string, unknown>> | null;
}

const PROTOCOL_FORMS_KEY = ["protocol-forms"];

export function useProtocolForms() {
  return useQuery({
    queryKey: PROTOCOL_FORMS_KEY,
    queryFn: () =>
      customInstance<ProtocolForm[]>({
        url: "/api/v1/protocol-forms",
        method: "GET",
      }),
  });
}

export function useCreateProtocolForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateProtocolFormInput) =>
      customInstance<ProtocolForm>({
        url: "/api/v1/protocol-forms",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOL_FORMS_KEY });
      showSuccess("Protocol form created");
    },
  });
}

export function useUpdateProtocolForm(formId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateProtocolFormInput) =>
      customInstance<ProtocolForm>({
        url: `/api/v1/protocol-forms/${formId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOL_FORMS_KEY });
      showSuccess("Protocol form updated");
    },
  });
}

export function useDeleteProtocolForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formId: string) =>
      customInstance<void>({
        url: `/api/v1/protocol-forms/${formId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOL_FORMS_KEY });
      showSuccess("Protocol form deleted");
    },
  });
}
