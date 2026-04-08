"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { CreateProtocolInput, Protocol } from "../types";

const PROTOCOLS_KEY = ["protocols"];

export function useProtocols(projectId?: string) {
  return useQuery({
    queryKey: projectId ? [...PROTOCOLS_KEY, { projectId }] : PROTOCOLS_KEY,
    queryFn: () =>
      customInstance<Protocol[]>({
        url: "/api/v1/protocols",
        method: "GET",
        ...(projectId ? { params: { project_id: projectId } } : {}),
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Protocol created"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Protocol published"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Protocol retired"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("New version created"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Protocol updated"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Protocol deleted"); },
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
      pick_list_values?: string[] | null;
      dose_response_config?: Record<string, unknown> | null;
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions`,
        method: "POST",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Readout definition added"); },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Readout definition removed"); },
  });
}

export function useAddConditionDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      data_type: string;
      unit?: string | null;
      pick_list_values?: string[] | null;
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/condition-definitions`,
        method: "POST",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Condition definition added"); },
  });
}

export function useRemoveConditionDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (definitionId: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/condition-definitions/${definitionId}`,
        method: "DELETE",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Condition definition removed"); },
  });
}

export function useSetControlLayout(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { plate_format: string; template_id: string }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/control-layouts`,
        method: "PUT",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Control layout set"); },
  });
}

export function useRemoveControlLayout(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (plateFormat: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/control-layouts/${plateFormat}`,
        method: "DELETE",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Control layout removed"); },
  });
}

export interface OntologyAnnotationInput {
  slot_name: string;
  terms: Array<{
    term_id: string;
    label: string;
    ontology_source: string;
    uri?: string | null;
  }>;
}

export function useSetOntologyAnnotation(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: OntologyAnnotationInput) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/ontology-annotations`,
        method: "PUT",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Annotation updated"); },
  });
}

export function useRemoveOntologyAnnotation(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slotName: string) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/ontology-annotations`,
        method: "DELETE",
        params: { slot_name: slotName },
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Annotation removed"); },
  });
}
