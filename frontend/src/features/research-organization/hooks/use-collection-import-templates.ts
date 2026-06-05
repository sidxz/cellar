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
 * List collection-import templates in the current workspace.
 *
 * When `collectionId` is provided, the server annotates each template with
 * `used_in_this_collection: boolean` based on whether the template has been
 * used on prior imports into that collection. The cache key includes the
 * collection id so prior-collection vs. workspace-wide views don't collide.
 *
 * Mutations in this module use a `["collection-import-templates"]` prefix on
 * `invalidateQueries`, which is a prefix-match in TanStack v5 and therefore
 * invalidates every per-collection variant on the next save/update/delete.
 */
export function useCollectionImportTemplates(collectionId?: string) {
  return useQuery({
    queryKey: [...TEMPLATES_QK, collectionId ?? null],
    queryFn: () => listCollectionImportTemplates({ collection_id: collectionId }),
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
    mutationFn: ({ templateId, body }) => updateCollectionImportTemplate(templateId, body),
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
