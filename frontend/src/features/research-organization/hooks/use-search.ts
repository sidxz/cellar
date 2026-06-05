"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useMutation } from "@tanstack/react-query";
import type { ActivityValue, ExecuteSearchInput, SortDir, SortField } from "../types";

export interface EnrichedSearchResponse {
  items: Molecule[];
  next_cursor: string | null;
  total_count: number | null;
  activity_data?: Record<string, Record<string, ActivityValue>>;
}

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
        url: "/api/v1/search/execute",
        method: "POST",
        data: params.input,
        params: Object.keys(searchParams).length ? searchParams : undefined,
      });
    },
  });
}
