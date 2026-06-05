"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface ImportTemplate {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  column_mappings: Record<string, string>;
  default_protocol_id: string | null;
  created_by: string;
}

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
        url: "/api/v1/import-templates",
        method: "GET",
      }),
  });
}

export function useCreateImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateImportTemplateInput) =>
      customInstance<ImportTemplate>({
        url: "/api/v1/import-templates",
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
        url: `/api/v1/import-templates/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMPORT_TEMPLATES_KEY });
      showSuccess("Import template deleted");
    },
  });
}
