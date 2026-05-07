"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

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
        url: "/api/v1/cdd-import/protocols",
        method: "GET",
      }),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 min — CDD protocols don't change often
  });
}

export function useCddProtocolPreview(externalId: number | null) {
  return useQuery({
    queryKey: ["cdd-import", "preview", externalId],
    queryFn: () =>
      customInstance<CddProtocolMappingResult>({
        url: `/api/v1/cdd-import/protocols/${externalId}/preview`,
        method: "GET",
      }),
    enabled: externalId !== null,
    staleTime: 5 * 60 * 1000,
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
        url: `/api/v1/cdd-import/protocols/${externalId}`,
        method: "POST",
        data: nameOverride ? { name_override: nameOverride } : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["protocols"] });
      showSuccess("Protocol imported from CDD Vault");
    },
  });
}
