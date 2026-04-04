"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateStorageLocationInput, StorageLocation } from "../types";

const STORAGE_KEY = ["storage-locations"];

export function useStorageLocations() {
  return useQuery({
    queryKey: STORAGE_KEY,
    queryFn: () =>
      customInstance<StorageLocation[]>({
        url: "/api/v1/storage-locations",
        method: "GET",
      }),
  });
}

export function useStorageLocationChildren(parentId: string | undefined) {
  return useQuery({
    queryKey: [...STORAGE_KEY, "children", parentId],
    queryFn: () =>
      customInstance<StorageLocation[]>({
        url: `/api/v1/storage-locations/${parentId}/children`,
        method: "GET",
      }),
    enabled: !!parentId,
  });
}

export function useCreateStorageLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateStorageLocationInput) =>
      customInstance<StorageLocation>({
        url: "/api/v1/storage-locations",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: STORAGE_KEY }),
  });
}
