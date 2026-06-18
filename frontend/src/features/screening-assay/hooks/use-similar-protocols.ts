"use client";

import { useDebounce } from "@/shared/hooks/use-debounce";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { SEARCH_DEBOUNCE_MS, SEARCH_MIN_QUERY_LEN } from "@/shared/lib/timing";
import { useQuery } from "@tanstack/react-query";

export interface SimilarProtocolTarget {
  id: string;
  name: string;
  target_type: string;
}

export interface SimilarProtocol {
  id: string;
  name: string;
  protocol_type: string;
  status: string;
  score: number;
  is_run_candidate: boolean;
  shared_readout_kinds: string[];
  targets: SimilarProtocolTarget[];
}

export interface SimilarProtocolDraft {
  name: string;
  protocol_type?: string | null;
  target_ids?: string[];
  readout_names?: string[];
  facet_ids?: string[];
}

export function useSimilarProtocols(draft: SimilarProtocolDraft) {
  const debouncedName = useDebounce(draft.name ?? "", SEARCH_DEBOUNCE_MS);
  return useQuery({
    queryKey: [
      "protocols",
      "similar",
      debouncedName,
      draft.protocol_type ?? null,
      draft.target_ids ?? [],
      draft.readout_names ?? [],
      draft.facet_ids ?? [],
    ],
    queryFn: () =>
      customInstance<SimilarProtocol[]>({
        url: `${API_V1}/protocols/similar`,
        method: "POST",
        data: {
          name: debouncedName,
          protocol_type: draft.protocol_type ?? null,
          target_ids: draft.target_ids ?? [],
          readout_names: draft.readout_names ?? [],
          facet_ids: draft.facet_ids ?? [],
          limit: 5,
        },
      }),
    enabled: debouncedName.trim().length >= SEARCH_MIN_QUERY_LEN,
  });
}
