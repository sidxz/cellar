"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

export interface CrudHooksConfig {
  entityName: string;
  baseUrl: string;
  queryKey: string[];
  parentQueryKeys?: string[][];
}

export function createCrudHooks<
  TEntity,
  TCreateInput = Record<string, unknown>,
  TUpdateInput = Record<string, unknown>,
>(config: CrudHooksConfig) {
  const { entityName, baseUrl, queryKey, parentQueryKeys = [] } = config;

  function invalidateAll(qc: QueryClient) {
    qc.invalidateQueries({ queryKey });
    for (const key of parentQueryKeys) {
      qc.invalidateQueries({ queryKey: key });
    }
  }

  function useList(
    params?: Record<string, string>,
    options?: Partial<UseQueryOptions<TEntity[]>>,
  ) {
    return useQuery({
      queryKey: params ? [...queryKey, params] : queryKey,
      queryFn: () =>
        customInstance<TEntity[]>({ url: baseUrl, method: "GET", params }),
      ...options,
    });
  }

  function useGet(
    id: string | undefined,
    options?: Partial<UseQueryOptions<TEntity>>,
  ) {
    return useQuery({
      queryKey: [...queryKey, id],
      queryFn: () =>
        customInstance<TEntity>({ url: `${baseUrl}/${id}`, method: "GET" }),
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
        showSuccess(`${entityName} created`);
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
        showSuccess(`${entityName} updated`);
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
        showSuccess(`${entityName} deleted`);
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
        showSuccess(successMessage ?? `${entityName} ${action} complete`);
      },
    });
  }

  return { useList, useGet, useCreate, useUpdate, useDelete, useAction };
}
