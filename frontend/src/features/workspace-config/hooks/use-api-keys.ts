"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

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

const API_KEYS_KEY = ["api-keys"];

export function useApiKeys() {
  return useQuery({
    queryKey: API_KEYS_KEY,
    queryFn: () =>
      customInstance<ExternalApiKey[]>({
        url: "/api/v1/api-keys",
        method: "GET",
      }),
  });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateApiKeyInput) =>
      customInstance<ExternalApiKey>({
        url: "/api/v1/api-keys",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_KEY });
      showSuccess("API key created");
    },
  });
}

export function useUpdateApiKey(keyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateApiKeyInput) =>
      customInstance<ExternalApiKey>({
        url: `/api/v1/api-keys/${keyId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_KEY });
      showSuccess("API key updated");
    },
  });
}

export function useDeleteApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      customInstance<void>({
        url: `/api/v1/api-keys/${keyId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_KEY });
      showSuccess("API key deleted");
    },
  });
}
