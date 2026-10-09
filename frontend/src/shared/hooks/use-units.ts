"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { UnitSuggestionResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export type UnitSuggestion = UnitSuggestionResponse;

export function useUnits() {
  return useQuery({
    queryKey: ["units"],
    queryFn: () => customInstance<UnitSuggestion[]>({ url: `${API_V1}/units`, method: "GET" }),
    staleTime: Number.POSITIVE_INFINITY,
  });
}
