"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  Collection,
  CreateCollectionInput,
  UpdateCollectionInput,
} from "../types";

const COLLECTIONS_KEY = ["collections"];

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

export function useCollection(id: string | undefined) {
  return useQuery({
    queryKey: [...COLLECTIONS_KEY, id],
    queryFn: () =>
      customInstance<Collection>({
        url: `/api/v1/collections/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateCollectionInput) =>
      customInstance<Collection>({
        url: "/api/v1/collections",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess("Collection created");
    },
  });
}

export function useUpdateCollection(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateCollectionInput) =>
      customInstance<Collection>({
        url: `/api/v1/collections/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess("Collection updated");
    },
  });
}

export function useDeleteCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/collections/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess("Collection deleted");
    },
  });
}
