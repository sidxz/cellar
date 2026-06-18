"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

export type VocabularyField = "readout_name" | "category";

export function useProtocolVocabulary(field: VocabularyField, q: string) {
  return useQuery({
    queryKey: ["protocols", "vocabulary", field, q],
    queryFn: () =>
      customInstance<string[]>({
        url: `${API_V1}/protocols/vocabulary`,
        method: "GET",
        params: { field, q: q || undefined, limit: 8 },
      }),
    enabled: q.trim().length > 0,
  });
}
