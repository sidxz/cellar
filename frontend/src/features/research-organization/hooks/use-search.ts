"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ExecuteSearchResponse } from "@/shared/lib/api/model";
import { useMutation } from "@tanstack/react-query";
import type { ActivityValue, ExecuteSearchInput, SortDir, SortField } from "../types";

/**
 * FE view of the `/search/execute` response. Derived from the generated
 * `ExecuteSearchResponse` for the structural fields, but two fields are
 * re-narrowed because the BE types them loosely:
 *  - `items`: generated as `MoleculeResponse[]`; the FE uses the
 *    chemical-registration `Molecule` domain alias (narrowed enums).
 *  - `activity_data`: the BE types this `dict[str, dict[str, Any]]`
 *    (search.py:165) so orval emits `unknown` values; the FE knows the blob
 *    is `Record<molId, Record<columnId, ActivityValue>>` (see ActivityValue
 *    in ../types). Residual: backend schema gap (untyped activity payload).
 */
export type EnrichedSearchResponse = Omit<ExecuteSearchResponse, "items" | "activity_data"> & {
  items: Molecule[];
  activity_data?: Record<string, Record<string, ActivityValue>>;
};

export function useExecuteSearch() {
  return useMutation({
    mutationFn: (params: {
      input: ExecuteSearchInput;
      cursor?: string;
      limit?: number;
      sort_by?: SortField;
      sort_dir?: SortDir;
    }) => {
      const searchParams: Record<string, string> = {};
      if (params.cursor) searchParams.cursor = params.cursor;
      if (params.limit) searchParams.limit = String(params.limit);
      if (params.sort_by) searchParams.sort_by = params.sort_by;
      if (params.sort_dir) searchParams.sort_dir = params.sort_dir;

      return customInstance<EnrichedSearchResponse>({
        url: `${API_V1}/search/execute`,
        method: "POST",
        data: params.input,
        params: Object.keys(searchParams).length ? searchParams : undefined,
      });
    },
  });
}
