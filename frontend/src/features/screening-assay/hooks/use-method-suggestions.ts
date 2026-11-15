"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  ConditionSuggestionResponse,
  MethodSuggestionsResponse,
  SuggestionsStatusResponse,
} from "@/shared/lib/api/model";
import { showError } from "@/shared/lib/toast";
import { useMutation, useQuery } from "@tanstack/react-query";

export type ConditionSuggestion = ConditionSuggestionResponse;

/** Whether this deployment suggests from a method: off unless a classifier is configured. */
export function useMethodSuggestionsEnabled(): boolean {
  const { data } = useQuery({
    queryKey: ["protocol-suggestions", "status"],
    queryFn: () =>
      customInstance<SuggestionsStatusResponse>({
        url: `${API_V1}/protocol-suggestions/status`,
        method: "GET",
      }),
    staleTime: Number.POSITIVE_INFINITY,
  });
  return data?.enabled ?? false;
}

/** Conditions the method names, for review. Nothing is saved. */
export function useSuggestFromMethod() {
  return useMutation({
    mutationFn: (method: string) =>
      customInstance<MethodSuggestionsResponse>({
        url: `${API_V1}/protocol-suggestions`,
        method: "POST",
        data: { method },
      }),
    onError: (err: Error) => showError(err.message),
  });
}
