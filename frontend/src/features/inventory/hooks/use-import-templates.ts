"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ImportTemplateResponse } from "@/shared/lib/api/model";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// Aggregate DTO — aliased to the orval-generated type (source of truth).
export type ImportTemplate = ImportTemplateResponse;

// Client-only form-input shape for the create mutation.
export interface CreateImportTemplateInput {
  name: string;
  column_mappings: Record<string, string>;
  description?: string | null;
  default_protocol_id?: string | null;
}

const IMPORT_TEMPLATES_KEY = ["import-templates"];

export function useImportTemplates() {
  return useQuery({
    queryKey: IMPORT_TEMPLATES_KEY,
    queryFn: () =>
      customInstance<ImportTemplate[]>({
        url: `${API_V1}/import-templates`,
        method: "GET",
      }),
  });
}

export function useCreateImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateImportTemplateInput) =>
      customInstance<ImportTemplate>({
        url: `${API_V1}/import-templates`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMPORT_TEMPLATES_KEY });
      showSuccess("Import template saved");
    },
  });
}

export function useDeleteImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `${API_V1}/import-templates/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMPORT_TEMPLATES_KEY });
      showSuccess("Import template deleted");
    },
  });
}
