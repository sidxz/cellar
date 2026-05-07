"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { CreateProtocolInput, Protocol } from "../types";

const PROTOCOLS_KEY = ["protocols"];

const protocolHooks = createCrudHooks<
  Protocol,
  CreateProtocolInput,
  {
    name?: string;
    description?: string | null;
    target_id?: string | null;
    category?: string | null;
    pos_control_signal?: "high" | "low";
  }
>({
  entityName: "Protocol",
  baseUrl: "/api/v1/protocols",
  queryKey: PROTOCOLS_KEY,
});

/** Custom list — supports optional projectId filter. */
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

export const useProtocol = protocolHooks.useGet;
export const useCreateProtocol = protocolHooks.useCreate;
export const useUpdateProtocol = protocolHooks.useUpdate;
export const useDeleteProtocol = protocolHooks.useDelete;

// --- State transitions (callers pass plain id string) ---

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

// --- Readout definitions (nested under protocol) ---

export function useAddReadoutDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      data_type: string;
      unit?: string | null;
      aggregation?: string;
      normalizations?: string[];
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

export function useUpdateReadoutDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      definitionId,
      data,
    }: {
      definitionId: string;
      data: {
        name?: string;
        data_type?: string;
        unit?: string | null;
        aggregation?: string;
        precision?: number | null;
        normalizations?: string[];
        normalization?: string;
        is_calculated?: boolean;
        calculation_formula?: string | null;
        display_order?: number;
        pick_list_values?: string[] | null;
        dose_response_config?: Record<string, unknown> | null;
      };
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions/${definitionId}`,
        method: "PUT",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Readout definition updated"); },
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

// --- Condition definitions (nested under protocol) ---

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

export function useUpdateConditionDefinition(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      definitionId,
      data,
    }: {
      definitionId: string;
      data: {
        name?: string;
        data_type?: string;
        unit?: string | null;
        pick_list_values?: string[] | null;
      };
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/condition-definitions/${definitionId}`,
        method: "PUT",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PROTOCOLS_KEY }); showSuccess("Condition definition updated"); },
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

// --- Control layouts (nested under protocol) ---

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

// --- Ontology annotations (nested under protocol) ---

export interface OntologyAnnotationInput {
  slot: string;
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
