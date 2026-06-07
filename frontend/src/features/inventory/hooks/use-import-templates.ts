"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";
import type { ImportTemplateResponse } from "@/shared/lib/api/model";

// Aggregate DTO — aliased to the orval-generated type (source of truth).
export type ImportTemplate = ImportTemplateResponse;

// Client-only form-input shape for the create mutation.
export interface CreateImportTemplateInput {
  name: string;
  column_mappings: Record<string, string>;
  description?: string | null;
  default_protocol_id?: string | null;
}

const importTemplateHooks = createCrudHooks<ImportTemplate, CreateImportTemplateInput>({
  entityName: "Import template",
  baseUrl: `${API_V1}/import-templates`,
  queryKey: ["import-templates"],
  messages: {
    created: () => "Import template saved",
  },
});

export const useImportTemplates = importTemplateHooks.useList;
export const useCreateImportTemplate = importTemplateHooks.useCreate;
export const useDeleteImportTemplate = importTemplateHooks.useDelete;
