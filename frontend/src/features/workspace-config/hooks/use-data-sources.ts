"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface IdStorageConfig {
  storage_type: "identifier" | "custom_field";
  identifier_type: string | null;
  custom_field_name: string | null;
}

export interface FieldMapping {
  source_field: string;
  target_field: string;
  target_type: "core" | "custom_field" | "identifier";
}

export interface EntityMapping {
  entity_type: string;
  id_field: string;
  id_storage: IdStorageConfig;
  field_mappings: FieldMapping[];
  parent_path?: string | null;
}

export interface DataSource {
  id: string;
  workspace_id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  api_key_name: string | null;
  is_active: boolean;
  create_batch_on_duplicate: boolean;
  entity_mappings: EntityMapping[];
  created_by: string;
  version: number;
}

export interface CreateDataSourceInput {
  name: string;
  source_type: string;
  config?: Record<string, unknown>;
  api_key_name?: string | null;
}

export interface UpdateDataSourceInput {
  name?: string;
  is_active?: boolean;
  create_batch_on_duplicate?: boolean | null;
  config?: Record<string, unknown>;
  api_key_name?: string | null;
  entity_mappings?: EntityMapping[];
}

// ---------------------------------------------------------------------------
// CRUD hooks
// ---------------------------------------------------------------------------

const dataSourceHooks = createCrudHooks<DataSource, CreateDataSourceInput, UpdateDataSourceInput>({
  entityName: "Data source",
  baseUrl: "/api/v1/data-sources",
  queryKey: ["data-sources"],
});

export const useDataSources = dataSourceHooks.useList;
export const useDataSource = dataSourceHooks.useGet;
export const useCreateDataSource = dataSourceHooks.useCreate;
export const useUpdateDataSource = dataSourceHooks.useUpdate;
export const useDeleteDataSource = dataSourceHooks.useDelete;

// ---------------------------------------------------------------------------
// Template preview (no auth needed)
// ---------------------------------------------------------------------------

export function useDataSourceTemplate(sourceType: string | null) {
  return useQuery({
    queryKey: ["data-sources", "templates", sourceType],
    queryFn: () =>
      customInstance<EntityMapping[]>({
        url: `/api/v1/data-sources/templates/${sourceType}`,
        method: "GET",
      }),
    enabled: !!sourceType,
  });
}
