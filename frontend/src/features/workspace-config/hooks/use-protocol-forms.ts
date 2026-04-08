"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";

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

const pfHooks = createCrudHooks<ProtocolForm, CreateProtocolFormInput, UpdateProtocolFormInput>({
  entityName: "Protocol form",
  baseUrl: "/api/v1/protocol-forms",
  queryKey: ["protocol-forms"],
});

export const useProtocolForms = pfHooks.useList;
export const useCreateProtocolForm = pfHooks.useCreate;
export const useUpdateProtocolForm = pfHooks.useUpdate;
export const useDeleteProtocolForm = pfHooks.useDelete;
