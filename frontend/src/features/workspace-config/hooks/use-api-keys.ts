"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";
import type {
  CreateExternalApiKeyBody,
  ExternalApiKeyResponse,
  UpdateExternalApiKeyBody,
} from "@/shared/lib/api/model";

// Aliases of the orval-generated DTOs (source of truth). Domain-friendly names
// keep call sites stable while the shapes stay in lockstep with the backend.
export type ExternalApiKey = ExternalApiKeyResponse;
export type CreateApiKeyInput = CreateExternalApiKeyBody;
export type UpdateApiKeyInput = UpdateExternalApiKeyBody;

const apiKeyHooks = createCrudHooks<ExternalApiKey, CreateApiKeyInput, UpdateApiKeyInput>({
  entityName: "API key",
  baseUrl: `${API_V1}/api-keys`,
  queryKey: ["api-keys"],
});

export const useApiKeys = apiKeyHooks.useList;
export const useCreateApiKey = apiKeyHooks.useCreate;
export const useUpdateApiKey = apiKeyHooks.useUpdate;
export const useDeleteApiKey = apiKeyHooks.useDelete;
