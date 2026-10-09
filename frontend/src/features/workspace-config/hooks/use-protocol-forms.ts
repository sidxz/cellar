"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateProtocolFormBody,
  ProtocolFormResponse,
  UpdateProtocolFormBody,
} from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

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

/** Adds the shipped default forms whose category exists and which the category lacks (existing forms untouched). */
export function useSeedDefaultProtocolForms() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customInstance<ProtocolForm[]>({ url: `${API_V1}/protocol-forms/defaults`, method: "POST" }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["protocol-forms"] });
      showSuccess(
        created.length > 0
          ? `Default forms added (${created.length})`
          : "No new default forms to add",
      );
    },
    onError: (err: Error) => showError(err.message),
  });
}
