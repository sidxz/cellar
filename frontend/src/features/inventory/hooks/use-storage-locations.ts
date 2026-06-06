"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { unwrapList } from "@/shared/types/pagination";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateStorageLocationInput,
  StorageLocation,
  StorageLocationWithCount,
  UpdateStorageLocationInput,
} from "../types";

const STORAGE_KEY = ["storage-locations"];

export function useStorageLocations() {
  return useQuery({
    queryKey: STORAGE_KEY,
    queryFn: async () => {
      const resp = await customInstance<StorageLocation[] | { items: StorageLocation[] }>({
        url: `${API_V1}/storage-locations`,
        method: "GET",
      });
      return unwrapList(resp);
    },
  });
}

export function useStorageLocationChildren(parentId: string | undefined) {
  return useQuery({
    queryKey: [...STORAGE_KEY, "children", parentId],
    queryFn: () =>
      customInstance<StorageLocation[]>({
        url: `${API_V1}/storage-locations/${parentId}/children`,
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
        url: `${API_V1}/storage-locations`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: STORAGE_KEY });
      showSuccess("Location created");
    },
  });
}

export function useUpdateStorageLocation(locationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateStorageLocationInput) =>
      customInstance<StorageLocation>({
        url: `${API_V1}/storage-locations/${locationId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: STORAGE_KEY });
      showSuccess("Location updated");
    },
  });
}

export function useDeleteStorageLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (locationId: string) =>
      customInstance<void>({
        url: `${API_V1}/storage-locations/${locationId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: STORAGE_KEY });
      showSuccess("Location deleted");
    },
  });
}

// ---------------------------------------------------------------------------
// Storage locations with sample counts
// ---------------------------------------------------------------------------

export function useStorageLocationsWithCounts() {
  return useQuery({
    queryKey: ["storage-locations", "with-counts"],
    queryFn: () =>
      customInstance<StorageLocationWithCount[]>({
        url: `${API_V1}/storage-locations-summary`,
        method: "GET",
      }),
  });
}
