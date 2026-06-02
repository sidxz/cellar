"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

/**
 * Custom list — supports optional projectId filter and tag filtering.
 *
 * - `projectId` scopes results to a single project.
 * - `tags` + `tagLogic` filter protocols by assigned tags (passed to the
 *   backend `tags` / `tag_logic` query params).
 */
export function useProtocols(
  projectId?: string,
  options?: { tags?: string[]; tagLogic?: "any" | "all" },
) {
  const tags = options?.tags?.length ? options.tags : null;
  return useQuery({
    queryKey: [
      ...PROTOCOLS_KEY,
      ...(projectId ? [{ projectId }] : []),
      ...(tags ? [{ tags, tagLogic: options?.tagLogic ?? "any" }] : []),
    ],
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (projectId) params.project_id = projectId;
      if (tags) { params.tags = tags; params.tag_logic = options?.tagLogic ?? "any"; }
      const resp = await customInstance<Protocol[] | { items: Protocol[] }>({
        url: "/api/v1/protocols",
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
      return Array.isArray(resp) ? resp : resp.items;
    },
  });
}

/** Lightweight protocol rows for the picker — name + status + run stats.
 *  Sorted server-side: most-recently-run first; never-run sink to bottom. */
export interface ProtocolSummary {
  id: string;
  name: string;
  status: string;
  protocol_type: string;
  description: string | null;
  target_id: string | null;
  target_name: string | null;
  run_count: number;
  /** ISO date (YYYY-MM-DD) or null when no runs yet. */
  last_run_date: string | null;
}

/**
 * Protocol picker rows (name + status + run stats).
 *
 * - `projectIds` empty / undefined ⇒ workspace-wide picker (every protocol).
 * - `projectIds` non-empty ⇒ scoped to the union of protocols linked to those
 *   projects, so a chemist on "Anti-inflammatory" doesn't have to scroll past
 *   200 unrelated assays in the dropdown.
 * - `includeAll = true` overrides scoping (backs the per-picker "Show all
 *   (across projects)" toggle for cross-program scaffold/selectivity lookups).
 */
export function useProtocolSummaries(projectIds?: string[], options?: { includeAll?: boolean }) {
  const includeAll = options?.includeAll ?? false;
  const scope = !includeAll && projectIds && projectIds.length > 0 ? [...projectIds].sort() : null;
  return useQuery({
    queryKey: scope
      ? [...PROTOCOLS_KEY, "summary", { projectIds: scope }]
      : [...PROTOCOLS_KEY, "summary"],
    queryFn: () =>
      customInstance<ProtocolSummary[]>({
        url: "/api/v1/protocols/summary",
        method: "GET",
        ...(scope ? { params: { project_ids: scope } } : {}),
      }),
  });
}

export const useProtocol = protocolHooks.useGet;
export const useCreateProtocol = protocolHooks.useCreate;
export const useUpdateProtocol = protocolHooks.useUpdate;
export const useDeleteProtocol = protocolHooks.useDelete;

// --- State transitions ---

export const usePublishProtocol = () => protocolHooks.useAction("publish", "Protocol published");
export const useRetireProtocol = () => protocolHooks.useAction("retire", "Protocol retired");
export const useLockProtocol = () => protocolHooks.useAction("lock", "Protocol locked");
export const useUnlockProtocol = () => protocolHooks.useAction("unlock", "Protocol unlocked");
export const useVersionProtocol = () => protocolHooks.useAction("version", "New version created");

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
      description?: string | null;
      pick_list_values?: Array<{ label: string; color?: string | null } | string> | null;
      dose_response_config?: Record<string, unknown> | null;
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Readout definition added");
    },
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
        description?: string | null;
        data_type?: string;
        unit?: string | null;
        aggregation?: string;
        precision?: number | null;
        normalizations?: string[];
        normalization?: string;
        is_calculated?: boolean;
        calculation_formula?: string | null;
        display_order?: number;
        pick_list_values?: Array<{ label: string; color?: string | null } | string> | null;
        dose_response_config?: Record<string, unknown> | null;
      };
    }) =>
      customInstance<Protocol>({
        url: `/api/v1/protocols/${protocolId}/readout-definitions/${definitionId}`,
        method: "PUT",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Readout definition updated");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Readout definition removed");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Condition definition added");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Condition definition updated");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Condition definition removed");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Control layout set");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Control layout removed");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Annotation updated");
    },
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Annotation removed");
    },
  });
}
