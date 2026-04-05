"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  CreateSavedSearchInput,
  SavedSearch,
  UpdateSavedSearchInput,
} from "../types";

const SAVED_SEARCHES_KEY = ["saved-searches"];

export function useSavedSearches(projectId?: string, mine?: boolean) {
  return useQuery({
    queryKey: [...SAVED_SEARCHES_KEY, { projectId, mine }],
    queryFn: () =>
      customInstance<SavedSearch[]>({
        url: "/api/v1/saved-searches",
        method: "GET",
        params: {
          ...(projectId ? { project_id: projectId } : {}),
          ...(mine ? { mine: "true" } : {}),
        },
      }),
  });
}

export function useSavedSearch(id: string | undefined) {
  return useQuery({
    queryKey: [...SAVED_SEARCHES_KEY, id],
    queryFn: () =>
      customInstance<SavedSearch>({
        url: `/api/v1/saved-searches/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateSavedSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSavedSearchInput) =>
      customInstance<SavedSearch>({
        url: "/api/v1/saved-searches",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAVED_SEARCHES_KEY });
      showSuccess("Saved search created");
    },
  });
}

export function useUpdateSavedSearch(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateSavedSearchInput) =>
      customInstance<SavedSearch>({
        url: `/api/v1/saved-searches/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAVED_SEARCHES_KEY });
      showSuccess("Saved search updated");
    },
  });
}

export function useDeleteSavedSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/saved-searches/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAVED_SEARCHES_KEY });
      showSuccess("Saved search deleted");
    },
  });
}
