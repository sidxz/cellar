"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import {
  type QueryClient,
  type UseQueryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

export interface CrudHooksConfig {
  entityName: string;
  baseUrl: string;
  queryKey: string[];
  parentQueryKeys?: string[][];
  /** Override per-action toast messages. Useful when the default
   * `${entityName} created` reads awkwardly or when consumers need
   * domain-specific phrasing. Receives the resolved entityName. */
  messages?: {
    created?: (entityName: string) => string;
    updated?: (entityName: string) => string;
    deleted?: (entityName: string) => string;
    actionDefault?: (entityName: string, action: string) => string;
  };
}

export function createCrudHooks<
  TEntity,
  TCreateInput = Record<string, unknown>,
  TUpdateInput = Record<string, unknown>,
>(config: CrudHooksConfig) {
  const { entityName, baseUrl, queryKey, parentQueryKeys = [], messages } = config;
  const createdMsg = messages?.created ?? ((n) => `${n} created`);
  const updatedMsg = messages?.updated ?? ((n) => `${n} updated`);
  const deletedMsg = messages?.deleted ?? ((n) => `${n} deleted`);
  const actionDefaultMsg = messages?.actionDefault ?? ((n, a) => `${n} ${a} complete`);

  function invalidateAll(qc: QueryClient) {
    qc.invalidateQueries({ queryKey });
    for (const key of parentQueryKeys) {
      qc.invalidateQueries({ queryKey: key });
    }
  }

  function useList(params?: Record<string, string>, options?: Partial<UseQueryOptions<TEntity[]>>) {
    return useQuery({
      queryKey: params ? [...queryKey, params] : queryKey,
      queryFn: async () => {
        // Endpoints migrated to cursor pagination return PaginatedResponse;
        // older ones still return a bare list. Accept both at runtime so
        // call sites don't need to know which shape they get.
        const resp = await customInstance<TEntity[] | { items: TEntity[] }>({
          url: baseUrl,
          method: "GET",
          params,
        });
        return Array.isArray(resp) ? resp : resp.items;
      },
      ...options,
    });
  }

  function useGet(id: string | undefined, options?: Partial<UseQueryOptions<TEntity>>) {
    return useQuery({
      queryKey: [...queryKey, id],
      queryFn: () => customInstance<TEntity>({ url: `${baseUrl}/${id}`, method: "GET" }),
      enabled: !!id,
      ...options,
    });
  }

  function useCreate() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (data: TCreateInput) =>
        customInstance<TEntity>({ url: baseUrl, method: "POST", data }),
      onSuccess: () => {
        invalidateAll(qc);
        showSuccess(createdMsg(entityName));
      },
      onError: (err: Error) => {
        showError(err.message || `Failed to create ${entityName}`);
      },
    });
  }

  function useUpdate(id: string) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (data: TUpdateInput) =>
        customInstance<TEntity>({
          url: `${baseUrl}/${id}`,
          method: "PATCH",
          data,
        }),
      onSuccess: () => {
        invalidateAll(qc);
        showSuccess(updatedMsg(entityName));
      },
      onError: (err: Error) => {
        showError(err.message || `Failed to update ${entityName}`);
      },
    });
  }

  function useDelete() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (id: string) =>
        customInstance<void>({ url: `${baseUrl}/${id}`, method: "DELETE" }),
      onSuccess: () => {
        invalidateAll(qc);
        showSuccess(deletedMsg(entityName));
      },
      onError: (err: Error) => {
        showError(err.message || `Failed to delete ${entityName}`);
      },
    });
  }

  function useAction(action: string, successMessage?: string) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: ({ id, data }: { id: string; data?: unknown }) =>
        customInstance<TEntity>({
          url: `${baseUrl}/${id}/${action}`,
          method: "POST",
          data,
        }),
      onSuccess: () => {
        invalidateAll(qc);
        showSuccess(successMessage ?? actionDefaultMsg(entityName, action));
      },
      onError: (err: Error) => {
        showError(err.message || `Failed to ${action} ${entityName}`);
      },
    });
  }

  return { useList, useGet, useCreate, useUpdate, useDelete, useAction };
}
