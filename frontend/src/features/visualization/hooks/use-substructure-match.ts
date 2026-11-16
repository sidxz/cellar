"use client";

import { API_V1, type ApiError, customInstance } from "@/shared/lib/api/custom-instance";
import type { SubstructureMatchRequest, SubstructureMatchResponse } from "@/shared/lib/api/model";
import { useMutation } from "@tanstack/react-query";

export type SubstructureMatchInput = {
  query: string;
  queryKind: "smiles" | "smarts";
  moleculeIds: string[];
};

/** Which of the given compounds contain the query, matched on the server the way Search
 * matches a substructure. */
export const matchSubstructure = ({ query, queryKind, moleculeIds }: SubstructureMatchInput) =>
  customInstance<SubstructureMatchResponse>({
    url: `${API_V1}/visualization/substructure-match`,
    method: "POST",
    data: {
      query,
      query_kind: queryKind,
      molecule_ids: moleculeIds,
    } satisfies SubstructureMatchRequest,
  });

export const useSubstructureMatch = () =>
  useMutation<SubstructureMatchResponse, ApiError, SubstructureMatchInput>({
    mutationFn: (input) => matchSubstructure(input),
  });
