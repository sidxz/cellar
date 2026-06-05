"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CompoundFlag } from "../types";

const FLAGS_KEY = ["compound-flags"];

export function useCompoundFlags(protocolId: string | undefined) {
  return useQuery<CompoundFlag[]>({
    queryKey: [...FLAGS_KEY, protocolId],
    queryFn: () =>
      customInstance<CompoundFlag[]>({
        url: `/api/v1/protocols/${protocolId}/flags`,
        method: "GET",
      }),
    enabled: !!protocolId,
  });
}

export function useCreateFlag(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      molecule_id: string;
      flag_type?: string;
      note?: string;
    }) =>
      customInstance<CompoundFlag>({
        url: `/api/v1/protocols/${protocolId}/flags`,
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FLAGS_KEY, protocolId] }),
  });
}

export function useDeleteFlag(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (flagId: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${protocolId}/flags/${flagId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...FLAGS_KEY, protocolId] }),
  });
}
