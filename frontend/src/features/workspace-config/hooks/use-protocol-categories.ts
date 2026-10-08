"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  CreateProtocolCategoryInput,
  ProtocolCategory,
  UpdateProtocolCategoryInput,
} from "../types";

const PROTOCOL_CATEGORIES_KEY = ["protocol-categories"];

const categoryHooks = createCrudHooks<
  ProtocolCategory,
  CreateProtocolCategoryInput,
  UpdateProtocolCategoryInput
>({
  entityName: "Category",
  baseUrl: `${API_V1}/protocol-categories`,
  queryKey: PROTOCOL_CATEGORIES_KEY,
});

export const useProtocolCategories = categoryHooks.useList;
export const useCreateProtocolCategory = categoryHooks.useCreate;
export const useUpdateProtocolCategory = categoryHooks.useUpdate;
export const useDeleteProtocolCategory = categoryHooks.useDelete;

/** Adds every shipped default category the workspace lacks (existing ones untouched). */
export function useSeedDefaultProtocolCategories() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customInstance<ProtocolCategory[]>({
        url: `${API_V1}/protocol-categories/defaults`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOL_CATEGORIES_KEY });
      showSuccess("Default categories added");
    },
    onError: (err: Error) => showError(err.message),
  });
}
