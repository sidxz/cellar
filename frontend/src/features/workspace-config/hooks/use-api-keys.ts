"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";

export interface ExternalApiKey {
  id: string;
  workspace_id: string;
  key_name: string;
  label: string;
  description: string | null;
  key_prefix: string;
  is_active: boolean;
  created_by: string;
  last_used_at: string | null;
}

export interface CreateApiKeyInput {
  key_name: string;
  label: string;
  description?: string | null;
  secret_value: string;
}

export interface UpdateApiKeyInput {
  label?: string;
  description?: string | null;
  secret_value?: string;
  is_active?: boolean;
}

const apiKeyHooks = createCrudHooks<ExternalApiKey, CreateApiKeyInput, UpdateApiKeyInput>({
  entityName: "API key",
  baseUrl: `${API_V1}/api-keys`,
  queryKey: ["api-keys"],
});

export const useApiKeys = apiKeyHooks.useList;
export const useCreateApiKey = apiKeyHooks.useCreate;
export const useUpdateApiKey = apiKeyHooks.useUpdate;
export const useDeleteApiKey = apiKeyHooks.useDelete;
