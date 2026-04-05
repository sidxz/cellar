"use client";

import { useMutation } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PaginatedResponse } from "@/shared/types/pagination";
import type { Molecule } from "@/features/chemical-registration/types";
import type { ExecuteSearchInput } from "../types";

export function useExecuteSearch() {
  return useMutation({
    mutationFn: (params: {
      input: ExecuteSearchInput;
      cursor?: string;
      limit?: number;
    }) => {
      const searchParams: Record<string, string> = {};
      if (params.cursor) searchParams.cursor = params.cursor;
      if (params.limit) searchParams.limit = String(params.limit);

      return customInstance<PaginatedResponse<Molecule>>({
        url: "/api/v1/search/execute",
        method: "POST",
        data: params.input,
        params: Object.keys(searchParams).length ? searchParams : undefined,
      });
    },
  });
}
