"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type {
  CreateNamingLabelInput,
  NamingLabel,
  NamingTermInUse,
  UpdateNamingLabelInput,
} from "../types";

const NAMING_LABELS_KEY = ["naming-labels"];

const labelHooks = createCrudHooks<NamingLabel, CreateNamingLabelInput, UpdateNamingLabelInput>({
  entityName: "Short label",
  baseUrl: `${API_V1}/naming-labels`,
  queryKey: NAMING_LABELS_KEY,
});

export const useNamingLabels = labelHooks.useList;
export const useCreateNamingLabel = labelHooks.useCreate;
export const useUpdateNamingLabel = labelHooks.useUpdate;
export const useDeleteNamingLabel = labelHooks.useDelete;

/** Every term protocol names draw on, its default short label and any override.
 *  Shares the labels key prefix, so label mutations refresh it too. */
export function useNamingTermsInUse() {
  return useQuery({
    queryKey: [...NAMING_LABELS_KEY, "terms-in-use"],
    queryFn: () =>
      customInstance<NamingTermInUse[]>({
        url: `${API_V1}/naming-labels/terms-in-use`,
        method: "GET",
      }),
  });
}
