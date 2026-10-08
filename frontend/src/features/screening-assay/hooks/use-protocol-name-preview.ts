"use client";

import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { useQuery } from "@tanstack/react-query";

export interface NamePreviewDraft {
  category: string | null;
  target_ids: string[];
  ontology_annotations: Record<string, OntologyTerm[]>;
  discriminator: string | null;
  protocol_id?: string;
}

/** The name these facts would generate. Debounces the draft by value (its JSON), so a
 *  caller may pass a fresh object every render without restarting the timer. */
export function useProtocolNamePreview(draft: NamePreviewDraft | null) {
  const key = useDebounce(draft ? JSON.stringify(draft) : null, 300);
  return useQuery({
    queryKey: ["protocols", "name-preview", key],
    queryFn: () =>
      customInstance<NamePreviewResponse>({
        url: `${API_V1}/protocols/name-preview`,
        method: "POST",
        data: JSON.parse(key as string),
      }),
    enabled: key !== null,
    placeholderData: (previous) => previous,
  });
}

/** Discriminators already in use; those on the same base name first when `base` is given. */
export function useDiscriminatorSuggestions(base: string | null, q: string): string[] {
  const debouncedQ = useDebounce(q, SEARCH_DEBOUNCE_MS);
  const { data } = useQuery({
    queryKey: ["protocols", "discriminators", base, debouncedQ],
    queryFn: () =>
      customInstance<string[]>({
        url: `${API_V1}/protocols/discriminators`,
        method: "GET",
        params: { base: base ?? undefined, q: debouncedQ || undefined },
      }),
  });
  return data ?? [];
}
