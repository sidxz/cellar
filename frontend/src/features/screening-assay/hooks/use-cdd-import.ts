"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface CddProtocolSummary {
  external_id: number;
  name: string;
  readout_count: number;
}

export interface MappedReadout {
  name: string;
  data_type: string;
  unit: string | null;
  aggregation: string;
  normalizations: string[];
  precision: number | null;
  pick_list_values: string[] | null;
  has_dose_response_config: boolean;
  /** Same shape as ReadoutDefinition.dose_response_config — surfaced so the
   *  import wizard can preview intercepts, range constraints, etc. */
  dose_response_config: Record<string, unknown> | null;
  display_order: number;
}

export interface MappedCondition {
  name: string;
  data_type: string;
  unit: string | null;
  pick_list_values: string[] | null;
}

export interface MappingWarning {
  field_name: string;
  source_type: string;
  reason: string;
}

export interface CddProtocolMappingResult {
  name: string;
  description: string | null;
  category: string | null;
  readouts: MappedReadout[];
  conditions: MappedCondition[];
  warnings: MappingWarning[];
  external_source_id: number;
}

const CDD_PROTOCOLS_KEY = ["cdd-import", "protocols"];

export function useCddProtocols(enabled: boolean) {
  return useQuery({
    queryKey: CDD_PROTOCOLS_KEY,
    queryFn: () =>
      customInstance<CddProtocolSummary[]>({
        url: `${API_V1}/cdd-import/protocols`,
        method: "GET",
      }),
    enabled,
    staleTime: STALE_TIME.MEDIUM, // CDD protocols don't change often
  });
}

export function useCddProtocolPreview(externalId: number | null) {
  return useQuery({
    queryKey: ["cdd-import", "preview", externalId],
    queryFn: () =>
      customInstance<CddProtocolMappingResult>({
        url: `${API_V1}/cdd-import/protocols/${externalId}/preview`,
        method: "GET",
      }),
    enabled: externalId !== null,
    staleTime: STALE_TIME.MEDIUM,
  });
}

export function useImportCddProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      externalId,
      nameOverride,
    }: {
      externalId: number;
      nameOverride?: string;
    }) =>
      customInstance({
        url: `${API_V1}/cdd-import/protocols/${externalId}`,
        method: "POST",
        data: nameOverride ? { name_override: nameOverride } : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["protocols"] });
      showSuccess("Protocol imported from CDD Vault");
    },
  });
}
