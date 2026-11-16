"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance, isStaleEdit } from "@/shared/lib/api/custom-instance";
import type {
  CreateSavedVisualizationBody,
  UpdateSavedVisualizationBody,
} from "@/shared/lib/api/model";
import { showError } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SavedView, SavedViewSummary } from "../types";
import { SAVED_VIEWS_KEY } from "./query-keys";

const BASE = `${API_V1}/saved-visualizations`;
const LIST_KEY = [...SAVED_VIEWS_KEY, "list"];

const hooks = createCrudHooks<
  SavedView,
  CreateSavedVisualizationBody,
  UpdateSavedVisualizationBody
>({ entityName: "View", baseUrl: BASE, queryKey: SAVED_VIEWS_KEY });

/** The views the caller can see that read ``protocolId`` (private ones only their owner's). */
export function useSavedViews(protocolId: string) {
  return useQuery({
    queryKey: [...LIST_KEY, { protocolId }],
    queryFn: () =>
      customInstance<SavedViewSummary[]>({
        url: BASE,
        method: "GET",
        params: { protocol_id: protocolId },
      }),
  });
}

/** One view, fetched once per opening: a background refetch would move its version under the
 * chemist's unsaved changes and let their next Save pass the stale-edit check. Dropped once
 * no page shows it, so the next opening fetches it as saved now. */
export const useSavedView = (id: string) =>
  hooks.useGet(id, {
    gcTime: 0,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

export const useCreateSavedView = hooks.useCreate;
export const useDeleteSavedView = hooks.useDelete;

/** PATCH a view; the open view takes the saved version. A stale edit (someone saved first,
 * or a save racing this one won) is the caller's to explain, so it gets no error toast. */
export function useUpdateSavedView(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { raceIsStale: true },
    mutationFn: (data: UpdateSavedVisualizationBody) =>
      customInstance<SavedView>({ url: `${BASE}/${id}`, method: "PATCH", data }),
    onSuccess: (view) => {
      qc.setQueryData([...SAVED_VIEWS_KEY, id], view);
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: (err: Error) => {
      if (!isStaleEdit(err, { race: true })) showError(err.message || "Failed to save the view");
    },
  });
}
