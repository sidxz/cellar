"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type {
  Collection,
  CreateCollectionInput,
  UpdateCollectionInput,
} from "../types";

const COLLECTIONS_KEY = ["collections"];

const collectionHooks = createCrudHooks<Collection, CreateCollectionInput, UpdateCollectionInput>({
  entityName: "Collection",
  baseUrl: "/api/v1/collections",
  queryKey: COLLECTIONS_KEY,
});

/** Custom list — supports optional projectId filter. */
export function useCollections(projectId?: string) {
  return useQuery({
    queryKey: projectId
      ? [...COLLECTIONS_KEY, { projectId }]
      : COLLECTIONS_KEY,
    queryFn: () =>
      customInstance<Collection[]>({
        url: "/api/v1/collections",
        method: "GET",
        ...(projectId ? { params: { project_id: projectId } } : {}),
      }),
  });
}

export const useCollection = collectionHooks.useGet;
export const useCreateCollection = collectionHooks.useCreate;
export const useUpdateCollection = collectionHooks.useUpdate;
export const useDeleteCollection = collectionHooks.useDelete;
