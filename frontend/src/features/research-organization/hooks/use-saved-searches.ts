"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type {
  CreateSavedSearchInput,
  SavedSearch,
  UpdateSavedSearchInput,
} from "../types";

const SAVED_SEARCHES_KEY = ["saved-searches"];

const savedSearchHooks = createCrudHooks<SavedSearch, CreateSavedSearchInput, UpdateSavedSearchInput>({
  entityName: "Saved search",
  baseUrl: "/api/v1/saved-searches",
  queryKey: SAVED_SEARCHES_KEY,
});

/** Custom list — supports optional projectId and mine filters. */
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

export const useSavedSearch = savedSearchHooks.useGet;
export const useCreateSavedSearch = savedSearchHooks.useCreate;
export const useUpdateSavedSearch = savedSearchHooks.useUpdate;
export const useDeleteSavedSearch = savedSearchHooks.useDelete;
