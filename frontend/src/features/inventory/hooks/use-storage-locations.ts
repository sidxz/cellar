"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { CreateStorageLocationInput, StorageLocation, UpdateStorageLocationInput } from "../types";

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
    onSuccess: () => { qc.invalidateQueries({ queryKey: STORAGE_KEY }); showSuccess("Location created"); },
  });
}

export function useUpdateStorageLocation(locationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateStorageLocationInput) =>
      customInstance<StorageLocation>({
        url: `/api/v1/storage-locations/${locationId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: STORAGE_KEY }); showSuccess("Location updated"); },
  });
}

export function useDeleteStorageLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (locationId: string) =>
      customInstance<void>({
        url: `/api/v1/storage-locations/${locationId}`,
        method: "DELETE",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: STORAGE_KEY }); showSuccess("Location deleted"); },
  });
}
