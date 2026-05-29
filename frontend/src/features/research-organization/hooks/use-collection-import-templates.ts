"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCollectionImportTemplateApiV1CollectionImportTemplatesPost as createCollectionImportTemplate,
  deleteCollectionImportTemplateApiV1CollectionImportTemplatesTemplateIdDelete as deleteCollectionImportTemplate,
  listCollectionImportTemplatesApiV1CollectionImportTemplatesGet as listCollectionImportTemplates,
  updateCollectionImportTemplateApiV1CollectionImportTemplatesTemplateIdPut as updateCollectionImportTemplate,
} from "@/shared/lib/api/collection-import/collection-import";
import type {
  CollectionImportTemplateResponse,
  CreateCollectionImportTemplateRequest,
  UpdateCollectionImportTemplateRequest,
} from "@/shared/lib/api/model";

const TEMPLATES_QK = ["collection-import-templates"] as const;

/**
 * List all collection-import templates in the current workspace.
 */
export function useCollectionImportTemplates() {
  return useQuery({
    queryKey: TEMPLATES_QK,
    queryFn: () => listCollectionImportTemplates(),
  });
}

/**
 * Create a new collection-import template; invalidates the list on success.
 */
export function useCreateCollectionImportTemplate() {
  const qc = useQueryClient();
  return useMutation<
    CollectionImportTemplateResponse,
    Error,
    CreateCollectionImportTemplateRequest
  >({
    mutationFn: (body) => createCollectionImportTemplate(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TEMPLATES_QK });
    },
  });
}

/**
 * Update an existing collection-import template; invalidates the list on success.
 */
export function useUpdateCollectionImportTemplate() {
  const qc = useQueryClient();
  return useMutation<
    CollectionImportTemplateResponse,
    Error,
    { templateId: string; body: UpdateCollectionImportTemplateRequest }
  >({
    mutationFn: ({ templateId, body }) =>
      updateCollectionImportTemplate(templateId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TEMPLATES_QK });
    },
  });
}

/**
 * Delete a collection-import template; invalidates the list on success.
 */
export function useDeleteCollectionImportTemplate() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (templateId) => deleteCollectionImportTemplate(templateId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TEMPLATES_QK });
    },
  });
}

export type {
  CollectionImportTemplateResponse,
  CreateCollectionImportTemplateRequest,
  UpdateCollectionImportTemplateRequest,
};
