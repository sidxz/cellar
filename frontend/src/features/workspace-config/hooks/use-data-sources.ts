"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateDataSourceBody,
  DataSourceResponse,
  EntityMappingResponse,
  UpdateDataSourceBody,
} from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// CLIENT-SIDE form-editor working types — NOT backend DTOs. The backend types
// `target_type` / `storage_type` as bare `str`, so the generated
// EntityMappingResponse widens them to `string`. The data-source mapping editor
// constrains them to the allowed values (enforced at runtime by its zod schema),
// so these narrowed shapes back the editable form state. They are narrowed from /
// validated against the generated EntityMappingResponse at the consumption edge.
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

// Aliases of the orval-generated DTOs (source of truth).
export type DataSource = DataSourceResponse;
export type CreateDataSourceInput = CreateDataSourceBody;
export type UpdateDataSourceInput = UpdateDataSourceBody;

// ---------------------------------------------------------------------------
// CRUD hooks
// ---------------------------------------------------------------------------

const dataSourceHooks = createCrudHooks<DataSource, CreateDataSourceInput, UpdateDataSourceInput>({
  entityName: "Data source",
  baseUrl: `${API_V1}/data-sources`,
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
      customInstance<EntityMappingResponse[]>({
        url: `${API_V1}/data-sources/templates/${sourceType}`,
        method: "GET",
      }),
    enabled: !!sourceType,
  });
}
