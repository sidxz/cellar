"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateProtocolInput, Protocol } from "../types";

const PROTOCOLS_KEY = ["protocols"];

export function useProtocols() {
  return useQuery({
    queryKey: PROTOCOLS_KEY,
    queryFn: () =>
      customInstance<Protocol[]>({
        url: "/api/v1/protocols",
        method: "GET",
      }),
  });
}

export function useProtocol(id: string | undefined) {
  return useQuery({
    queryKey: [...PROTOCOLS_KEY, id],
    queryFn: () =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateProtocolInput) =>
      customInstance<Protocol>({
        url: "/api/v1/protocols",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function usePublishProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${id}/publish`,
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useRetireProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string | null }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${id}/retire`,
        method: "POST",
        data: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useVersionProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${id}/version`,
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useUpdateProtocol(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name?: string; description?: string | null; target_id?: string | null; category?: string | null }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useDeleteProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/protocols/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useAddReadoutDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      data_type: string;
      unit?: string | null;
      aggregation?: string;
      normalization?: string;
      is_calculated?: boolean;
      calculation_formula?: string | null;
      display_order?: number;
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions`,
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}

export function useRemoveReadoutDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (definitionId: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions/${definitionId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }),
  });
}
