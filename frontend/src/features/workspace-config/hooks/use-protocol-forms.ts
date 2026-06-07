"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";
import type {
  CreateProtocolFormBody,
  ProtocolFormResponse,
  UpdateProtocolFormBody,
} from "@/shared/lib/api/model";

// Aliases of the orval-generated DTOs (source of truth). The template fields
// (readout_templates / condition_templates / ontology_defaults) resolve to the
// generated opaque-record item types — derive, never redeclare.
export type ProtocolForm = ProtocolFormResponse;
export type CreateProtocolFormInput = CreateProtocolFormBody;
export type UpdateProtocolFormInput = UpdateProtocolFormBody;

const pfHooks = createCrudHooks<ProtocolForm, CreateProtocolFormInput, UpdateProtocolFormInput>({
  entityName: "Protocol form",
  baseUrl: `${API_V1}/protocol-forms`,
  queryKey: ["protocol-forms"],
});

export const useProtocolForms = pfHooks.useList;
export const useCreateProtocolForm = pfHooks.useCreate;
export const useUpdateProtocolForm = pfHooks.useUpdate;
export const useDeleteProtocolForm = pfHooks.useDelete;
