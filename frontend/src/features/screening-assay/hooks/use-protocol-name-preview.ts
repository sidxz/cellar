"use client";

import { useDebounce } from "@/shared/hooks/use-debounce";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { NamePreviewRequest, NamePreviewResponse } from "@/shared/lib/api/model";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { useQuery } from "@tanstack/react-query";

/** The facts a name would be generated from. Typed off the DTO. */
export type NamePreviewDraft = NamePreviewRequest;

/** One preview query for a draft serialized as JSON: shared by the dialog and the CSV import. */
export const namePreviewQuery = (draftJson: string) => ({
  queryKey: ["protocols", "name-preview", draftJson],
  queryFn: () =>
    customInstance<NamePreviewResponse>({
      url: `${API_V1}/protocols/name-preview`,
      method: "POST",
      data: JSON.parse(draftJson),
    }),
});

/** The name these facts would generate. Debounces the draft by value (its JSON), so a
 *  caller may pass a fresh object every render without restarting the timer. No draft
 *  (null) means no preview at once: the last name is not kept for a cleared form. */
export function useProtocolNamePreview(draft: NamePreviewDraft | null) {
  const debounced = useDebounce(draft ? JSON.stringify(draft) : null, 300);
  const key = draft ? debounced : null;
  return useQuery({
    ...namePreviewQuery(key as string),
    enabled: key !== null,
    placeholderData: (previous) => (key === null ? undefined : previous),
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
